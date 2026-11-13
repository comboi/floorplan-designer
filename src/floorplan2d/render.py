"""Render SVG del plano (Y hacia arriba) y conversión opcional a PNG."""
from __future__ import annotations

import math
from html import escape
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from .model import Item, Plan
from .validate import Issue

PALETTE = ["#9ec5fe", "#a3cfbb", "#ffda6a", "#f1aeb5", "#c5b3e6", "#a6e9d5", "#fcc89b", "#b6bfc9"]
WALL = "#3a3f47"


def _polys(g: BaseGeometry) -> list[Polygon]:
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [p for geom in getattr(g, "geoms", []) for p in _polys(geom)]


def _color_map(plan: Plan) -> dict[str, str]:
    keys: list[str] = []
    for it in plan.items:
        k = it.group or it.base_id
        if k not in keys:
            keys.append(k)
    return {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(keys)}


def _fmt_len(plan: Plan, v: float) -> str:
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{s} {plan.units}"


def render_svg(plan: Plan, issues: list[Issue] | None = None, *, show_zones: bool = True,
               show_dims: bool = True, show_labels: bool = True, px_per_m: float = 100.0) -> str:
    issues = issues or []
    k = px_per_m / (1000.0 / plan.unit_mm)  # px por unidad del plano
    minx, miny, maxx, maxy = plan.outer.bounds
    margin = 70.0
    legend_h = 26.0 + 18.0 * ((len(set(_color_map(plan).values())) + 3) // 4)
    width = (maxx - minx) * k + 2 * margin
    height = (maxy - miny) * k + 2 * margin + legend_h

    def X(x: float) -> float:
        return margin + (x - minx) * k

    def Y(y: float) -> float:
        return margin + (maxy - y) * k

    def path(g: BaseGeometry) -> str:
        parts = []
        for p in _polys(g):
            for ring in [p.exterior, *p.interiors]:
                pts = " L".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in ring.coords)
                parts.append(f"M{pts} Z")
        return " ".join(parts)

    cmap = _color_map(plan)
    out: list[str] = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.2f} {height:.2f}" font-family="Helvetica, Arial, sans-serif">')
    a(f'<rect width="100%" height="100%" fill="#ffffff"/>')
    a(f'<text x="{margin}" y="28" font-size="16" font-weight="700" fill="#1f2933">{escape(plan.name)}</text>')
    sq = plan.area_m2(plan.room.area)
    a(f'<text x="{margin}" y="46" font-size="11" fill="#52606d">{sq:.1f} m² útiles · unidades: {plan.units}</text>')

    # suelo
    a(f'<path d="{path(plan.room)}" fill="#fafafa" stroke="none"/>')

    # zonas libres
    if show_zones:
        for it in plan.items:
            for side, zone in it.zones.items():
                a(f'<path d="{path(zone)}" fill="#f4a261" fill-opacity="0.22" stroke="#e76f51" stroke-width="0.8" stroke-dasharray="4 3"/>')

    # muros y aberturas
    a(f'<path d="{path(plan.walls)}" fill="{WALL}" fill-rule="evenodd" stroke="none"/>')
    for op in plan.openings:
        if op.kind == "window":
            for t in (0.35, 0.65):
                x0 = op.start[0] - op.n[0] * plan.thickness * t
                y0 = op.start[1] - op.n[1] * plan.thickness * t
                x1 = op.end[0] - op.n[0] * plan.thickness * t
                y1 = op.end[1] - op.n[1] * plan.thickness * t
                a(f'<line x1="{X(x0):.2f}" y1="{Y(y0):.2f}" x2="{X(x1):.2f}" y2="{Y(y1):.2f}" stroke="#5aa9e6" stroke-width="2"/>')
        elif op.kind == "door" and op.arc:
            hx, hy = op.hinge_pt
            lx, ly = op.leaf_end
            a(f'<line x1="{X(hx):.2f}" y1="{Y(hy):.2f}" x2="{X(lx):.2f}" y2="{Y(ly):.2f}" stroke="{WALL}" stroke-width="2.5"/>')
            pts = " ".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in op.arc)
            a(f'<polyline points="{pts}" fill="none" stroke="{WALL}" stroke-width="0.9" stroke-dasharray="3 2"/>')

    # objetos
    for it in plan.items:
        fill = it.color or cmap[it.group or it.base_id]
        a(f'<path d="{path(it.footprint)}" fill="{fill}" stroke="#1f2933" stroke-width="1.2"/>')
        fx = it.center[0] + it.front[0] * it.d / 2
        fy = it.center[1] + it.front[1] * it.d / 2
        ex = it.center[0] + it.front[0] * (it.d / 2 - min(it.d / 2, 8 / k))
        ey = it.center[1] + it.front[1] * (it.d / 2 - min(it.d / 2, 8 / k))
        a(f'<line x1="{X(ex):.2f}" y1="{Y(ey):.2f}" x2="{X(fx):.2f}" y2="{Y(fy):.2f}" stroke="#1f2933" stroke-width="1.6"/>')
        if show_labels:
            _label(out, it, X, Y, k)

    # incidencias
    for iss in issues:
        if iss.where is None or iss.where.is_empty:
            continue
        color = "#d00000" if iss.severity == "error" else "#e09f00"
        a(f'<path d="{path(iss.where)}" fill="{color}" fill-opacity="0.45" stroke="{color}" stroke-width="1.4"/>')

    if show_dims:
        _dimensions(out, plan, X, Y, k)

    _legend(out, plan, cmap, margin, height - legend_h + 6, width)
    a("</svg>")
    return "\n".join(out)


def _label(out: list[str], it: Item, X, Y, k: float) -> None:
    cx, cy = X(it.center[0]), Y(it.center[1])
    box_w, box_h = it.w * k, it.d * k
    # texto horizontal; si el objeto es estrecho para la etiqueta, se reduce o gira
    size = max(7.0, min(12.0, min(box_w, box_h) / 4.2))
    txt = it.label
    fits = len(txt) * size * 0.58 <= max(box_w, box_h) * 0.9
    rot = ""
    if min(box_w, box_h) < size * 1.6 and box_h > box_w:
        rot = f' transform="rotate(-90 {cx:.2f} {cy:.2f})"'
    if not fits and len(txt) > 4:
        txt = txt[: max(3, int(max(box_w, box_h) * 0.9 / (size * 0.58)) - 1)] + "…"
    out.append(
        f'<text x="{cx:.2f}" y="{cy - 1:.2f}" font-size="{size:.1f}" text-anchor="middle" fill="#102a43" font-weight="600"{rot}>{escape(txt)}</text>'
    )
    dim = f"{it.w:g}×{it.d:g}" if it.shape == "rect" else f"Ø{it.w:g}"
    out.append(
        f'<text x="{cx:.2f}" y="{cy + size:.2f}" font-size="{max(6.0, size * 0.72):.1f}" text-anchor="middle" fill="#486581"{rot}>{dim}</text>'
    )


def _dimensions(out: list[str], plan: Plan, X, Y, k: float) -> None:
    """Cotas de los bordes del recinto, por el exterior del muro."""
    off = max(plan.thickness * k, 4.0) + 16
    for e in plan.edges:
        mx, my = (e.p0[0] + e.p1[0]) / 2, (e.p0[1] + e.p1[1]) / 2
        nx, ny = -e.n[0], -e.n[1]  # hacia fuera
        ax, ay = X(e.p0[0]) + nx * off, Y(e.p0[1]) - ny * off
        bx, by = X(e.p1[0]) + nx * off, Y(e.p1[1]) - ny * off
        out.append(f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{bx:.2f}" y2="{by:.2f}" stroke="#7b8794" stroke-width="0.8"/>')
        for px, py, qx, qy in ((ax, ay, X(e.p0[0]) + nx * 6, Y(e.p0[1]) - ny * 6), (bx, by, X(e.p1[0]) + nx * 6, Y(e.p1[1]) - ny * 6)):
            out.append(f'<line x1="{px:.2f}" y1="{py:.2f}" x2="{qx:.2f}" y2="{qy:.2f}" stroke="#7b8794" stroke-width="0.8"/>')
        tx, ty = X(mx) + nx * (off + 9), Y(my) - ny * (off + 9)
        ang = math.degrees(math.atan2(-(by - ay), bx - ax)) * -1
        if ang > 90 or ang < -90:
            ang += 180
        out.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" font-size="10" text-anchor="middle" fill="#52606d" transform="rotate({ang:.1f} {tx:.2f} {ty:.2f})">{escape(_fmt_len(plan, e.length))}</text>'
        )


def _legend(out: list[str], plan: Plan, cmap: dict[str, str], x0: float, y0: float, width: float) -> None:
    col_w = max(150.0, (width - 2 * x0) / 4)
    for n, (name, color) in enumerate(cmap.items()):
        cx = x0 + (n % 4) * col_w
        cy = y0 + (n // 4) * 18
        out.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="11" height="11" fill="{color}" stroke="#1f2933" stroke-width="0.8"/>')
        out.append(f'<text x="{cx + 16:.1f}" y="{cy + 9.5:.1f}" font-size="10.5" fill="#323f4b">{escape(name)}</text>')


def svg_to_png(svg: str, out_path: Path, scale: float = 2.0) -> bool:
    """PNG con resvg-py (extra `png`; wheels autocontenidas, sin librerías del sistema).

    Devuelve False si no está instalado.
    """
    try:
        import resvg_py  # type: ignore
    except Exception:
        return False
    out_path.write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=scale)))
    return True
