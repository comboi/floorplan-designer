"""Validación genérica de un plano: sin reglas de ningún tipo de local.

Comprobaciones:
  OUTSIDE   objeto (parcialmente) fuera del recinto
  OVERLAP   dos objetos se solapan (salvo `overlap_ok: true`)
  CLEARANCE zona libre de un objeto ocupada por otro objeto o fuera del recinto
  SWING     el giro de una puerta choca con un objeto
  OPENING   un objeto bloquea el hueco de una abertura
  NARROW    paso entre objetos (o objeto y muro) menor que `rules.min_gap`
  GAP       incumple una regla `rules.gaps` (min/max entre selectores)
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .model import TOL, Item, Plan

AREA_EPS = 1e-4  # en unidades² (evita falsos positivos por redondeo)


@dataclass
class Issue:
    severity: str  # error | warning
    code: str
    message: str
    ids: tuple[str, ...] = ()
    where: BaseGeometry | None = None


def _fmt(plan: Plan, v: float) -> str:
    return f"{v:.0f} {plan.units}" if abs(v - round(v)) < 0.05 else f"{v:.1f} {plan.units}"


def validate(plan: Plan) -> list[Issue]:
    issues: list[Issue] = []
    room = plan.room

    for it in plan.items:
        outside = it.footprint.difference(room)
        if outside.area > AREA_EPS:
            issues.append(Issue("error", "OUTSIDE", f"{it.id} sobresale del recinto ({_fmt(plan, outside.area ** 0.5)} aprox.)", (it.id,), outside))

    for a, b in combinations(plan.items, 2):
        if a.overlap_ok or b.overlap_ok:
            continue
        inter = a.footprint.intersection(b.footprint)
        if inter.area > AREA_EPS:
            issues.append(Issue("error", "OVERLAP", f"{a.id} y {b.id} se solapan", (a.id, b.id), inter))

    for it in plan.items:
        for side, zone in it.zones.items():
            _check_zone(plan, issues, it, side, zone)

    for op in plan.openings:
        if op.swing_zone is not None:
            for it in plan.items:
                hit = it.footprint.intersection(op.swing_zone)
                if hit.area > AREA_EPS and not it.overlap_ok:
                    issues.append(Issue("error", "SWING", f"{it.id} obstruye el giro de la puerta {op.id}", (op.id, it.id), hit))
        free = _opening_free_zone(op)
        for it in plan.items:
            blocked = it.footprint.intersection(free)
            if blocked.area > AREA_EPS and not it.overlap_ok:
                issues.append(Issue("error", "OPENING", f"{it.id} bloquea la abertura {op.id}", (op.id, it.id), blocked))

    if plan.rules.min_gap > 0:
        issues.extend(_narrow(plan))
    issues.extend(_gap_rules(plan))
    return issues


def _opening_free_zone(op) -> BaseGeometry:
    """Franja frente al hueco (ancho del hueco × 40 % de su ancho, mínimo 1 unidad) hacia el interior."""
    depth = max(op.width * 0.4, 1.0)
    n = op.n
    s, e = op.start, op.end
    return Polygon([s, e, (e[0] + n[0] * depth, e[1] + n[1] * depth), (s[0] + n[0] * depth, s[1] + n[1] * depth)])


def _check_zone(plan: Plan, issues: list[Issue], it: Item, side: str, zone: BaseGeometry) -> None:
    for other in plan.items:
        if other.id == it.id or other.overlap_ok:
            continue
        hit = zone.intersection(other.footprint)
        if hit.area > AREA_EPS:
            issues.append(
                Issue(
                    "error",
                    "CLEARANCE",
                    f"{other.id} invade la zona libre {side} de {it.id} ({_fmt(plan, it.clearance[side])} requeridos)",
                    (it.id, other.id),
                    hit,
                )
            )
    outside = zone.difference(plan.room)
    if outside.area > AREA_EPS:
        issues.append(
            Issue(
                "warning",
                "CLEARANCE",
                f"la zona libre {side} de {it.id} ({_fmt(plan, it.clearance[side])}) sale del recinto",
                (it.id,),
                outside,
            )
        )


def _narrow(plan: Plan) -> list[Issue]:
    out: list[Issue] = []
    mg = plan.rules.min_gap
    boundary = plan.room.exterior
    for a, b in combinations(plan.items, 2):
        if a.overlap_ok or b.overlap_ok or a.narrow_ok or b.narrow_ok:
            continue
        d = a.footprint.distance(b.footprint)
        if TOL < d < mg - TOL:
            out.append(Issue("warning", "NARROW", f"paso de {_fmt(plan, d)} entre {a.id} y {b.id} (mínimo {_fmt(plan, mg)})", (a.id, b.id)))
    for it in plan.items:
        if it.overlap_ok or it.narrow_ok:
            continue
        d = it.footprint.distance(boundary)
        if TOL < d < mg - TOL and plan.room.contains(it.footprint):
            out.append(Issue("warning", "NARROW", f"paso de {_fmt(plan, d)} entre {it.id} y el muro (mínimo {_fmt(plan, mg)})", (it.id,)))
    return out


def _gap_rules(plan: Plan) -> list[Issue]:
    out: list[Issue] = []
    for rule in plan.rules.gaps:
        A, B = plan.select(rule.a), plan.select(rule.b)
        if not A or not B:
            missing = rule.a if not A else rule.b
            out.append(Issue("warning", "GAP", f"regla gaps: el selector {missing!r} no coincide con ningún objeto"))
            continue
        for a in A:
            others = [b for b in B if b.id != a.id]
            if not others:
                continue
            dists = [(a.footprint.distance(b.footprint), b) for b in others]
            if rule.min is not None:
                for d, b in dists:
                    if d < rule.min - TOL:
                        out.append(Issue("error", "GAP", f"{a.id} a {_fmt(plan, d)} de {b.id}; mínimo {_fmt(plan, rule.min)}", (a.id, b.id)))
            if rule.max is not None:
                d, b = min(dists, key=lambda t: t[0])
                if d > rule.max + TOL:
                    out.append(Issue("error", "GAP", f"{a.id} a {_fmt(plan, d)} de {b.id} (el más cercano); máximo {_fmt(plan, rule.max)}", (a.id, b.id)))
    return out


def summary(plan: Plan) -> dict:
    """Métricas básicas: áreas y porcentaje de ocupación (en m²)."""
    room_area = plan.room.area
    occupied = sum(i.footprint.area for i in plan.items)
    return {
        "room_area_m2": round(plan.area_m2(room_area), 2),
        "items_area_m2": round(plan.area_m2(occupied), 2),
        "occupancy_pct": round(100 * occupied / room_area, 1) if room_area else 0.0,
        "items": len(plan.items),
    }
