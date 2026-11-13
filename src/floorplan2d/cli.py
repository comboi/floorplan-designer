"""CLI: floorplan new | check | build | catalog | install-skill"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .model import PlanError, load_plan
from .validate import summary, validate

SKILL_NAME = "floorplan-2d"


def _res(*parts: str) -> Path:
    return Path(str(resources.files("floorplan2d").joinpath(*parts)))


# --------------------------------------------------------------------------- #
def cmd_new(a: argparse.Namespace) -> int:
    dst = Path(a.path)
    if dst.exists() and not a.force:
        print(f"error: {dst} ya existe (usa --force para sobrescribir)", file=sys.stderr)
        return 2
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_res("templates", "plan.yaml"), dst)
    cat = dst.parent / "catalog.yaml"
    if not cat.exists():
        shutil.copyfile(_res("templates", "catalog.yaml"), cat)
        print(f"creado {cat}")
    print(f"creado {dst}")
    print(f"siguiente: floorplan build {dst}")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    try:
        plan = load_plan(a.plan)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    issues = validate(plan)
    if a.json:
        print(json.dumps({"summary": summary(plan), "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message, "ids": list(i.ids)} for i in issues]}, ensure_ascii=False, indent=2))
    else:
        _print_report(plan, issues)
    errors = sum(1 for i in issues if i.severity == "error")
    return 1 if errors else 0


def _print_report(plan, issues) -> None:
    s = summary(plan)
    print(f"{plan.name}: {s['room_area_m2']} m² · {s['items']} objetos · ocupación {s['occupancy_pct']} %")
    if not issues:
        print("sin incidencias")
        return
    for i in issues:
        mark = "ERROR" if i.severity == "error" else "aviso"
        print(f"  [{mark}] {i.code}: {i.message}")
    e = sum(1 for i in issues if i.severity == "error")
    w = len(issues) - e
    print(f"{e} error(es), {w} aviso(s)")


def cmd_build(a: argparse.Namespace) -> int:
    from .dxf import export_dxf
    from .render import render_svg, svg_to_png

    try:
        plan = load_plan(a.plan)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    issues = validate(plan)
    out_dir = Path(a.out) if a.out else Path(a.plan).resolve().parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(a.plan).stem
    formats = set(a.format or ["svg", "dxf"])

    svg = render_svg(plan, issues, show_zones=not a.no_zones, show_dims=not a.no_dims, show_labels=not a.no_labels)
    written = []
    if "svg" in formats or "png" in formats:
        p = out_dir / f"{stem}.svg"
        p.write_text(svg, encoding="utf-8")
        written.append(p)
    if "png" in formats:
        png = out_dir / f"{stem}.png"
        if svg_to_png(svg, png):
            written.append(png)
        else:
            print("aviso: PNG requiere resvg-py (pip install 'floorplan-2d[png]'); se deja el SVG", file=sys.stderr)
    if "dxf" in formats:
        p = out_dir / f"{stem}.dxf"
        export_dxf(plan, p, include_zones=not a.no_zones)
        written.append(p)

    _print_report(plan, issues)
    for p in written:
        print(f"→ {p}")
    errors = sum(1 for i in issues if i.severity == "error")
    return 1 if (errors and a.strict) else 0


def cmd_catalog(a: argparse.Namespace) -> int:
    import yaml

    path = Path(a.file) if a.file else _res("templates", "catalog.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for name, d in data.items():
        size = d.get("size") or d.get("diameter")
        grp = d.get("group", "")
        print(f"{name:<22} {str(size):<14} {grp}")
    return 0


def cmd_install_skill(a: argparse.Namespace) -> int:
    if a.global_:
        dest_root = Path.home() / ".claude" / "skills"
    else:
        dest_root = Path(a.workspace or ".").resolve() / ".claude" / "skills"
    dest = dest_root / SKILL_NAME
    src = _res("skill")
    if dest.exists():
        if not a.force:
            print(f"error: {dest} ya existe (usa --force para actualizarla)", file=sys.stderr)
            return 2
        shutil.rmtree(dest)
    dest_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "VERSION").write_text(__version__ + "\n", encoding="utf-8")
    print(f"skill instalada en {dest}")
    print("reinicia la sesión de Claude Code en ese workspace para que la cargue")
    return 0


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="floorplan", description="Planos 2D en planta desde YAML (SVG/PNG/DXF) con validación.")
    ap.add_argument("--version", action="version", version=f"floorplan-2d {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="crea plan.yaml y catalog.yaml de ejemplo")
    s.add_argument("path", nargs="?", default="plan.yaml")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("check", help="valida el plano (código de salida 1 si hay errores)")
    s.add_argument("plan")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("build", help="valida y exporta SVG/PNG/DXF")
    s.add_argument("plan")
    s.add_argument("-o", "--out", help="carpeta de salida (por defecto ./out junto al plan)")
    s.add_argument("-f", "--format", action="append", choices=["svg", "png", "dxf"], help="repetible; por defecto svg y dxf")
    s.add_argument("--no-zones", action="store_true", help="oculta las zonas libres")
    s.add_argument("--no-dims", action="store_true", help="oculta las cotas del recinto")
    s.add_argument("--no-labels", action="store_true", help="oculta etiquetas de objetos")
    s.add_argument("--strict", action="store_true", help="código de salida 1 si hay errores de validación")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("catalog", help="lista las piezas de un catálogo")
    s.add_argument("file", nargs="?")
    s.set_defaults(fn=cmd_catalog)

    s = sub.add_parser("install-skill", help="instala la skill de Claude Code en un workspace o globalmente")
    s.add_argument("workspace", nargs="?", help="carpeta del workspace (por defecto la actual)")
    s.add_argument("--global", dest="global_", action="store_true", help="instala en ~/.claude/skills")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_install_skill)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
