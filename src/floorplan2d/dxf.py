"""Exportación DXF con ezdxf. Un archivo, capas con intención, texto en capa propia.

Capas: WALLS, OPENINGS, ITEMS, ITEMS-TEXT, CLEARANCE, DIMENSIONS.
Unidades: se declara $INSUNITS según `units` del plano; las coordenadas no se escalan.
"""
from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from ezdxf import units as ezunits
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from .model import Plan

LAYERS = {
    "WALLS": 7,
    "OPENINGS": 5,
    "ITEMS": 3,
    "ITEMS-TEXT": 2,
    "CLEARANCE": 30,
    "DIMENSIONS": 8,
}
INSUNITS = {"mm": ezunits.MM, "cm": ezunits.CM, "m": ezunits.M}


def _polys(g: BaseGeometry) -> list[Polygon]:
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [p for geom in getattr(g, "geoms", []) for p in _polys(geom)]


def export_dxf(plan: Plan, path: Path, *, include_zones: bool = True) -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = INSUNITS[plan.units]
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()

    # muros: contorno exterior e interior (los huecos de puertas/ventanas ya están restados)
    for poly in _polys(plan.walls):
        for ring in [poly.exterior, *poly.interiors]:
            msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": "WALLS"})

    for op in plan.openings:
        if op.kind == "window":
            msp.add_line(op.start, op.end, dxfattribs={"layer": "OPENINGS"})
        elif op.kind == "door" and op.arc:
            msp.add_line(op.hinge_pt, op.leaf_end, dxfattribs={"layer": "OPENINGS"})
            msp.add_lwpolyline(op.arc, dxfattribs={"layer": "OPENINGS"})
        else:
            msp.add_line(op.start, op.end, dxfattribs={"layer": "OPENINGS", "linetype": "DASHED"})

    th = max(plan.room.bounds[2] - plan.room.bounds[0], plan.room.bounds[3] - plan.room.bounds[1]) * 0.012
    for it in plan.items:
        coords = list(it.footprint.exterior.coords)[:-1]
        msp.add_lwpolyline(coords, close=True, dxfattribs={"layer": "ITEMS"})
        dim = f"{it.w:g}x{it.d:g}" if it.shape == "rect" else f"D{it.w:g}"
        t = msp.add_text(f"{it.label} {dim}", height=th, dxfattribs={"layer": "ITEMS-TEXT"})
        t.set_placement(it.center, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        if include_zones:
            for zone in it.zones.values():
                for poly in _polys(zone):
                    msp.add_lwpolyline(list(poly.exterior.coords)[:-1], close=True, dxfattribs={"layer": "CLEARANCE"})

    # cotas de los bordes del recinto, por fuera del muro. El tamaño del texto y de las flechas
    # se escala con el plano: el estilo por defecto de ezdxf está pensado para ~mm y saldría diminuto.
    # dimlfac=1: el estilo EZDXF trae ×100 (metros→cm) y las cotas saldrían multiplicadas.
    override = {
        "dimtxt": th, "dimasz": th, "dimexe": th * 0.5, "dimexo": th * 0.5, "dimgap": th * 0.3,
        "dimlfac": 1.0, "dimdec": 0, "dimzin": 8,
    }
    for e in plan.edges:
        dist = plan.thickness + th * 4
        base = (
            (e.p0[0] + e.p1[0]) / 2 - e.n[0] * dist,
            (e.p0[1] + e.p1[1]) / 2 - e.n[1] * dist,
        )
        angle = math.degrees(math.atan2(e.d[1], e.d[0]))
        if angle > 90.0 + 1e-9 or angle <= -90.0 + 1e-9:
            angle += 180.0  # el texto de la cota se lee siempre derecho, no boca abajo
        msp.add_linear_dim(
            base=base, p1=e.p0, p2=e.p1, angle=angle, override=override, dxfattribs={"layer": "DIMENSIONS"}
        ).render()

    doc.saveas(str(path))
