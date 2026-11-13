"""Carga de un plano desde YAML y construcción de su geometría (shapely).

Convenciones (documentadas también en la skill):
  * Coordenadas con Y hacia arriba (norte). Unidades: mm, cm o m (campo `units`).
  * Los bordes del recinto se numeran siguiendo el orden de los vértices. En un
    rectángulo `width x depth`: 0 = sur (izq→der), 1 = este (sur→norte),
    2 = norte (der→izq), 3 = oeste (norte→sur).
  * Un objeto tiene ancho (eje local x) y fondo (eje local y). Su FRENTE es el
    lado +y local; con rotación 0 mira al norte. `rotate` gira en sentido
    antihorario alrededor de su centro.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
SIDES = ("front", "back", "left", "right")
CLEARANCE_KEYS = SIDES + ("all",)
TOL = 1e-6


class PlanError(ValueError):
    """Error de formato en el YAML del plano."""


# --------------------------------------------------------------------------- #
# Estructuras
# --------------------------------------------------------------------------- #
@dataclass
class Edge:
    index: int
    p0: tuple[float, float]
    p1: tuple[float, float]
    length: float
    d: tuple[float, float]  # dirección unitaria p0→p1
    n: tuple[float, float]  # normal unitaria hacia el interior


@dataclass
class Opening:
    id: str
    kind: str  # door | window | opening
    edge: int
    offset: float
    width: float
    swing: str  # in | out | none
    hinge: str  # start | end
    start: tuple[float, float]
    end: tuple[float, float]
    n: tuple[float, float]
    d: tuple[float, float]
    cut: Polygon  # hueco que se resta del muro
    hinge_pt: tuple[float, float] | None = None
    leaf_end: tuple[float, float] | None = None  # extremo de la hoja abierta
    arc: list[tuple[float, float]] = field(default_factory=list)
    swing_zone: Polygon | None = None


@dataclass
class Item:
    id: str
    base_id: str
    label: str
    group: str | None
    shape: str  # rect | circle
    w: float
    d: float
    center: tuple[float, float]
    rotation: float
    color: str | None
    overlap_ok: bool
    narrow_ok: bool
    clearance: dict[str, float]
    footprint: Polygon
    zones: dict[str, BaseGeometry]
    front: tuple[float, float]  # vector unitario del frente


@dataclass
class GapRule:
    a: str
    b: str
    min: float | None = None
    max: float | None = None


@dataclass
class Rules:
    min_gap: float = 0.0
    gaps: list[GapRule] = field(default_factory=list)


@dataclass
class Plan:
    name: str
    units: str
    points: list[tuple[float, float]]
    room: Polygon
    edges: list[Edge]
    thickness: float
    outer: Polygon
    walls: BaseGeometry
    openings: list[Opening]
    items: list[Item]
    rules: Rules
    source: Path | None = None

    @property
    def unit_mm(self) -> float:
        return UNIT_TO_MM[self.units]

    def area_m2(self, area_units2: float) -> float:
        return area_units2 * (self.unit_mm / 1000.0) ** 2

    def select(self, selector: str) -> list[Item]:
        """`group:x`, `id:x` o `x` (id, id base de un repeat, o grupo)."""
        sel = str(selector).strip()
        if sel.startswith("group:"):
            g = sel[6:]
            return [i for i in self.items if i.group == g]
        if sel.startswith("id:"):
            sel = sel[3:]
            return [i for i in self.items if i.id == sel or i.base_id == sel]
        found = [i for i in self.items if i.id == sel or i.base_id == sel]
        return found or [i for i in self.items if i.group == sel]


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _num(value: Any, what: str) -> float:
    if isinstance(value, bool):
        raise PlanError(f"{what}: se esperaba un número, llegó {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise PlanError(f"{what}: se esperaba un número, llegó {value!r}") from None


def _pair(value: Any, what: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise PlanError(f"{what}: se esperaba [x, y], llegó {value!r}")
    return (_num(value[0], what), _num(value[1], what))


def _signed_area(pts: list[tuple[float, float]]) -> float:
    s = 0.0
    for i, (x0, y0) in enumerate(pts):
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _edges(points: list[tuple[float, float]], sign: int) -> list[Edge]:
    edges = []
    for i, p0 in enumerate(points):
        p1 = points[(i + 1) % len(points)]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < TOL:
            raise PlanError(f"El borde {i} del recinto tiene longitud 0")
        d = (dx / length, dy / length)
        n = (-d[1], d[0]) if sign > 0 else (d[1], -d[0])
        edges.append(Edge(i, p0, p1, length, d, n))
    return edges


def _place(local: BaseGeometry, center: tuple[float, float], rot_deg: float) -> BaseGeometry:
    g = affinity.rotate(local, rot_deg, origin=(0, 0))
    return affinity.translate(g, center[0], center[1])


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
def load_plan(path: str | Path) -> Plan:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PlanError(f"No existe el archivo {path}") from None
    except yaml.YAMLError as exc:
        raise PlanError(f"YAML inválido en {path}: {exc}") from None
    if not isinstance(data, dict):
        raise PlanError("El plano debe ser un mapa YAML (name, units, room, items…)")
    return build_plan(data, base_dir=path.parent, source=path)


def build_plan(data: dict, base_dir: Path | None = None, source: Path | None = None) -> Plan:
    base_dir = base_dir or Path.cwd()
    units = str(data.get("units", "cm"))
    if units not in UNIT_TO_MM:
        raise PlanError(f"units debe ser una de {sorted(UNIT_TO_MM)}, llegó {units!r}")

    room_raw = data.get("room")
    if not isinstance(room_raw, dict):
        raise PlanError("Falta `room` (con width/depth o polygon)")
    points = _room_points(room_raw)
    poly = Polygon(points)
    if not poly.is_valid or poly.area < TOL:
        raise PlanError("El polígono del recinto no es válido (¿se cruza o tiene área 0?)")
    sign = 1 if _signed_area(points) > 0 else -1
    edges = _edges(points, sign)

    default_thickness = 200.0 / UNIT_TO_MM[units]  # 20 cm
    thickness = _num(room_raw.get("wall_thickness", default_thickness), "room.wall_thickness")
    if thickness < 0:
        raise PlanError("room.wall_thickness no puede ser negativo")
    outer = poly.buffer(thickness, join_style=2) if thickness > 0 else poly

    catalog = _load_catalog(data.get("catalog"), base_dir)
    openings = _build_openings(data.get("openings") or [], edges, thickness)
    walls = outer.difference(poly)
    if openings:
        walls = walls.difference(unary_union([o.cut for o in openings]))

    items = _build_items(data.get("items") or [], catalog, edges, sign)
    _ensure_unique([i.id for i in items], "objeto")
    rules = _build_rules(data.get("rules") or {})

    return Plan(
        name=str(data.get("name", "Plano")),
        units=units,
        points=points,
        room=poly,
        edges=edges,
        thickness=thickness,
        outer=outer,
        walls=walls,
        openings=openings,
        items=items,
        rules=rules,
        source=source,
    )


def _room_points(room: dict) -> list[tuple[float, float]]:
    ox, oy = _pair(room.get("origin", [0, 0]), "room.origin")
    if "polygon" in room:
        raw = room["polygon"]
        if not isinstance(raw, list) or len(raw) < 3:
            raise PlanError("room.polygon necesita al menos 3 vértices [[x,y], …]")
        pts = [_pair(p, "room.polygon") for p in raw]
    elif "width" in room and "depth" in room:
        w = _num(room["width"], "room.width")
        d = _num(room["depth"], "room.depth")
        if w <= 0 or d <= 0:
            raise PlanError("room.width y room.depth deben ser > 0")
        pts = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]
    else:
        raise PlanError("room necesita `width` y `depth`, o `polygon`")
    return [(x + ox, y + oy) for x, y in pts]


def _load_catalog(spec: Any, base_dir: Path) -> dict[str, dict]:
    if spec is None:
        return {}
    if isinstance(spec, dict):
        return spec
    files = [spec] if isinstance(spec, str) else spec
    if not isinstance(files, list):
        raise PlanError("`catalog` debe ser un archivo, una lista de archivos o un mapa")
    merged: dict[str, dict] = {}
    for f in files:
        p = (base_dir / str(f)).expanduser()
        try:
            loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            raise PlanError(f"No existe el catálogo {p}") from None
        except yaml.YAMLError as exc:
            raise PlanError(f"YAML inválido en el catálogo {p}: {exc}") from None
        if not isinstance(loaded, dict):
            raise PlanError(f"El catálogo {p} debe ser un mapa nombre → definición")
        merged.update(loaded)
    return merged


def _ensure_unique(ids: list[str], what: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise PlanError(f"Id de {what} duplicado: {i!r}")
        seen.add(i)


# --------------------------------------------------------------------------- #
# Aberturas
# --------------------------------------------------------------------------- #
def _build_openings(raw_list: list, edges: list[Edge], thickness: float) -> list[Opening]:
    out: list[Opening] = []
    for n, raw in enumerate(raw_list, 1):
        if not isinstance(raw, dict):
            raise PlanError(f"openings[{n}] debe ser un mapa")
        kind = str(raw.get("type", "door"))
        if kind not in ("door", "window", "opening"):
            raise PlanError(f"openings[{n}].type debe ser door, window u opening")
        oid = str(raw.get("id", f"{kind}-{n}"))
        if "wall" not in raw:
            raise PlanError(f"La abertura {oid!r} necesita `wall` (índice del borde)")
        ei = int(_num(raw["wall"], f"{oid}.wall"))
        if not 0 <= ei < len(edges):
            raise PlanError(f"{oid}: wall={ei} fuera de rango (hay {len(edges)} bordes)")
        e = edges[ei]
        width = _num(raw.get("width"), f"{oid}.width")
        offset = _num(raw.get("offset", 0), f"{oid}.offset")
        if width <= 0:
            raise PlanError(f"{oid}: width debe ser > 0")
        if offset < -TOL or offset + width > e.length + 1e-6:
            raise PlanError(
                f"{oid}: no cabe en el borde {ei} (longitud {e.length:g}); offset+width = {offset + width:g}"
            )
        swing = str(raw.get("swing", "in" if kind == "door" else "none"))
        hinge = str(raw.get("hinge", "start"))
        if swing not in ("in", "out", "none") or hinge not in ("start", "end"):
            raise PlanError(f"{oid}: swing in|out|none y hinge start|end")
        start = (e.p0[0] + e.d[0] * offset, e.p0[1] + e.d[1] * offset)
        end = (start[0] + e.d[0] * width, start[1] + e.d[1] * width)
        eps = max(thickness * 0.02, 1e-3)
        n = e.n
        cut = Polygon(
            [
                (start[0] + n[0] * eps, start[1] + n[1] * eps),
                (end[0] + n[0] * eps, end[1] + n[1] * eps),
                (end[0] - n[0] * (thickness + eps), end[1] - n[1] * (thickness + eps)),
                (start[0] - n[0] * (thickness + eps), start[1] - n[1] * (thickness + eps)),
            ]
        )
        op = Opening(oid, kind, ei, offset, width, swing, hinge, start, end, n, e.d, cut)
        if kind == "door" and swing in ("in", "out"):
            _door_geometry(op)
        out.append(op)
    _ensure_unique([o.id for o in out], "abertura")
    return out


def _door_geometry(op: Opening, steps: int = 16) -> None:
    h = op.start if op.hinge == "start" else op.end
    other = op.end if op.hinge == "start" else op.start
    ux, uy = other[0] - h[0], other[1] - h[1]
    ln = math.hypot(ux, uy)
    u = (ux / ln, uy / ln)
    s = op.n if op.swing == "in" else (-op.n[0], -op.n[1])
    a0, a1 = math.atan2(u[1], u[0]), math.atan2(s[1], s[0])
    delta = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    r = op.width
    op.arc = [
        (h[0] + r * math.cos(a0 + delta * k / steps), h[1] + r * math.sin(a0 + delta * k / steps))
        for k in range(steps + 1)
    ]
    op.hinge_pt = h
    op.leaf_end = (h[0] + s[0] * r, h[1] + s[1] * r)
    op.swing_zone = Polygon([h, *op.arc])


# --------------------------------------------------------------------------- #
# Objetos
# --------------------------------------------------------------------------- #
def _resolve_use(raw: dict, catalog: dict[str, dict]) -> dict:
    use = raw.get("use")
    if use is None:
        return dict(raw)
    if use not in catalog:
        known = ", ".join(sorted(map(str, catalog))) or "(catálogo vacío)"
        raise PlanError(f"`use: {use}` no está en el catálogo. Disponibles: {known}")
    base = catalog[use]
    if not isinstance(base, dict):
        raise PlanError(f"La entrada de catálogo {use!r} debe ser un mapa")
    merged = dict(base)
    merged.update({k: v for k, v in raw.items() if k != "use"})
    return merged


def _build_items(raw_items: list, catalog: dict, edges: list[Edge], sign: int) -> list[Item]:
    out: list[Item] = []
    for n, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict):
            raise PlanError(f"items[{n}] debe ser un mapa")
        merged = _resolve_use(raw, catalog)
        base_id = str(merged.get("id") or merged.get("use") or f"item{n}")
        rep = merged.get("repeat") or {}
        count = int(_num(rep.get("count", 1), f"{base_id}.repeat.count")) if rep else 1
        if count < 1:
            raise PlanError(f"{base_id}: repeat.count debe ser ≥ 1")
        step = rep.get("step") if rep else None
        for k in range(count):
            item_id = base_id if count == 1 else f"{base_id}-{k + 1}"
            out.append(_make_item(merged, item_id, base_id, k, step, edges, sign))
    return out


def _make_item(r: dict, item_id: str, base_id: str, k: int, step: Any, edges: list[Edge], sign: int) -> Item:
    shape = str(r.get("shape", "rect"))
    if shape not in ("rect", "circle"):
        raise PlanError(f"{item_id}: shape debe ser rect o circle")
    size = r.get("size")
    if shape == "circle":
        diameter = r.get("diameter")
        if diameter is None and isinstance(size, (list, tuple)) and size:
            diameter = size[0]
        elif diameter is None and isinstance(size, (int, float)):
            diameter = size
        w = d = _num(diameter, f"{item_id}.diameter")
    else:
        w, d = _pair(size, f"{item_id}.size")
    if w <= 0 or d <= 0:
        raise PlanError(f"{item_id}: las medidas deben ser > 0")

    extra_rot = _num(r.get("rotate", 0), f"{item_id}.rotate")
    if "wall" in r and "at" in r:
        raise PlanError(f"{item_id}: usa `at` o `wall`, no ambos")
    if "wall" in r:
        wl = r["wall"]
        if not isinstance(wl, dict) or "edge" not in wl:
            raise PlanError(f"{item_id}: wall debe ser {{edge: N, offset: X, gap: Y, align: start|center|end}}")
        ei = int(_num(wl["edge"], f"{item_id}.wall.edge"))
        if not 0 <= ei < len(edges):
            raise PlanError(f"{item_id}: wall.edge={ei} fuera de rango (hay {len(edges)} bordes)")
        e = edges[ei]
        gap = _num(wl.get("gap", 0), f"{item_id}.wall.gap")
        offset = _num(wl.get("offset", 0), f"{item_id}.wall.offset")
        if k:
            if not isinstance(step, (int, float)):
                raise PlanError(f"{base_id}: con `wall`, repeat.step debe ser un número (separación a lo largo del muro)")
            offset += k * float(step)
        align = str(wl.get("align", "start"))
        if align == "center":
            off = (e.length - w) / 2 + offset
        elif align == "end":
            off = e.length - w - offset
        elif align == "start":
            off = offset
        else:
            raise PlanError(f"{item_id}: wall.align debe ser start, center o end")
        center = (
            e.p0[0] + e.d[0] * (off + w / 2) + e.n[0] * (d / 2 + gap),
            e.p0[1] + e.d[1] * (off + w / 2) + e.n[1] * (d / 2 + gap),
        )
        rotation = math.degrees(math.atan2(e.d[1], e.d[0])) + (0 if sign > 0 else 180) + extra_rot
    elif "at" in r:
        x, y = _pair(r["at"], f"{item_id}.at")
        if k:
            if not isinstance(step, (list, tuple)):
                raise PlanError(f"{base_id}: con `at`, repeat.step debe ser [dx, dy]")
            dx, dy = _pair(step, f"{base_id}.repeat.step")
            x, y = x + k * dx, y + k * dy
        anchor = str(r.get("anchor", "center"))
        if anchor == "bl":
            x, y = x + w / 2, y + d / 2
        elif anchor != "center":
            raise PlanError(f"{item_id}: anchor debe ser center o bl")
        center = (x, y)
        rotation = extra_rot
    else:
        raise PlanError(f"{item_id}: falta la posición (`at: [x, y]` o `wall: {{edge, offset}}`)")

    if shape == "circle":
        local: BaseGeometry = Point(0, 0).buffer(w / 2, quad_segs=24)
    else:
        local = box(-w / 2, -d / 2, w / 2, d / 2)
    footprint = _place(local, center, rotation)

    clearance = _parse_clearance(r.get("clearance"), item_id)
    zones = _zones(local, w, d, clearance, shape, center, rotation)
    rad = math.radians(rotation)
    front = (-math.sin(rad), math.cos(rad))  # +y local rotado

    color = r.get("color")
    if color is not None and not (isinstance(color, str) and color.startswith("#") and len(color) in (4, 7)):
        raise PlanError(f"{item_id}: color debe ser hexadecimal (#rgb o #rrggbb)")
    group = r.get("group")
    return Item(
        id=item_id,
        base_id=base_id,
        label=str(r.get("label", base_id)),
        group=str(group) if group is not None else None,
        shape=shape,
        w=w,
        d=d,
        center=center,
        rotation=rotation,
        color=color,
        overlap_ok=bool(r.get("overlap_ok", False)),
        narrow_ok=bool(r.get("narrow_ok", False)),
        clearance=clearance,
        footprint=footprint,
        zones=zones,
        front=front,
    )


def _parse_clearance(raw: Any, item_id: str) -> dict[str, float]:
    if raw is None:
        return {}
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return {"front": float(raw)} if raw > 0 else {}
    if not isinstance(raw, dict):
        raise PlanError(f"{item_id}: clearance debe ser un número (frente) o un mapa {list(CLEARANCE_KEYS)}")
    out = {}
    for key, val in raw.items():
        if key not in CLEARANCE_KEYS:
            raise PlanError(f"{item_id}: clearance.{key} no válido (usa {', '.join(CLEARANCE_KEYS)})")
        v = _num(val, f"{item_id}.clearance.{key}")
        if v > 0:
            out[key] = v
    return out


def _zones(local, w, d, clearance, shape, center, rotation) -> dict[str, BaseGeometry]:
    zones: dict[str, BaseGeometry] = {}
    hw, hd = w / 2, d / 2
    shapes = {
        "front": lambda v: box(-hw, hd, hw, hd + v),
        "back": lambda v: box(-hw, -hd - v, hw, -hd),
        "left": lambda v: box(-hw - v, -hd, -hw, hd),
        "right": lambda v: box(hw, -hd, hw + v, hd),
    }
    for side, v in clearance.items():
        if side == "all":
            ring = local.buffer(v, join_style=1 if shape == "circle" else 2).difference(local)
            zones["all"] = _place(ring, center, rotation)
        else:
            zones[side] = _place(shapes[side](v), center, rotation)
    return zones


# --------------------------------------------------------------------------- #
# Reglas
# --------------------------------------------------------------------------- #
def _build_rules(raw: dict) -> Rules:
    if not isinstance(raw, dict):
        raise PlanError("`rules` debe ser un mapa")
    rules = Rules(min_gap=_num(raw.get("min_gap", 0), "rules.min_gap"))
    for n, g in enumerate(raw.get("gaps") or [], 1):
        if not isinstance(g, dict) or "a" not in g or "b" not in g:
            raise PlanError(f"rules.gaps[{n}] necesita `a` y `b` (id, `id:x` o `group:x`)")
        mn = _num(g["min"], f"rules.gaps[{n}].min") if "min" in g else None
        mx = _num(g["max"], f"rules.gaps[{n}].max") if "max" in g else None
        if mn is None and mx is None:
            raise PlanError(f"rules.gaps[{n}] necesita `min` y/o `max`")
        rules.gaps.append(GapRule(str(g["a"]), str(g["b"]), mn, mx))
    return rules
