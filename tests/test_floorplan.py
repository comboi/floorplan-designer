from pathlib import Path

import ezdxf
import pytest

from floorplan2d.cli import main
from floorplan2d.model import PlanError, build_plan
from floorplan2d.render import render_svg
from floorplan2d.validate import validate


def plan(items=None, openings=None, rules=None, room=None, catalog=None):
    data = {
        "units": "cm",
        "room": room or {"width": 600, "depth": 400, "wall_thickness": 20},
        "items": items or [],
        "openings": openings or [],
        "rules": rules or {},
    }
    if catalog:
        data["catalog"] = catalog
    return build_plan(data)


def codes(p):
    return sorted(i.code for i in validate(p))


def test_clean_plan_has_no_issues():
    p = plan([{"id": "a", "size": [100, 50], "at": [300, 200]}])
    assert validate(p) == []


def test_overlap_and_outside():
    p = plan([
        {"id": "a", "size": [100, 100], "at": [300, 200]},
        {"id": "b", "size": [100, 100], "at": [350, 200]},
        {"id": "c", "size": [100, 100], "at": [580, 200]},
    ])
    c = codes(p)
    assert "OVERLAP" in c and "OUTSIDE" in c


def test_touching_is_not_overlap():
    p = plan([
        {"id": "a", "size": [100, 100], "at": [300, 200]},
        {"id": "b", "size": [100, 100], "at": [400, 200]},
    ])
    assert "OVERLAP" not in codes(p)


def test_overlap_ok_is_respected():
    p = plan([
        {"id": "a", "size": [100, 100], "at": [300, 200]},
        {"id": "b", "size": [100, 100], "at": [350, 200], "overlap_ok": True},
    ])
    assert "OVERLAP" not in codes(p)


def test_clearance_front_is_invaded_in_front_only():
    base = {"id": "a", "size": [100, 50], "at": [300, 100], "clearance": {"front": 80}}
    # sin rotación el frente mira al norte (+y): un objeto al norte lo invade…
    p = plan([base, {"id": "b", "size": [40, 40], "at": [300, 170]}])
    assert "CLEARANCE" in codes(p)
    # …y uno al sur (detrás) no
    p = plan([base, {"id": "b", "size": [40, 40], "at": [300, 40]}])
    assert "CLEARANCE" not in codes(p)


def test_rotation_turns_the_front():
    # rotate 90 (antihorario): el frente pasa de norte a oeste
    a = {"id": "a", "size": [100, 50], "at": [300, 200], "rotate": 90, "clearance": {"front": 80}}
    west = plan([a, {"id": "b", "size": [30, 30], "at": [215, 200]}])
    north = plan([a, {"id": "b", "size": [30, 30], "at": [300, 260]}])
    assert "CLEARANCE" in codes(west)
    assert "CLEARANCE" not in codes(north)


def test_wall_placement_faces_into_room_on_every_edge():
    for edge in range(4):
        p = plan([{"id": "a", "size": [100, 40], "wall": {"edge": edge, "align": "center"}}])
        it = p.items[0]
        assert p.room.contains(it.footprint.buffer(-1e-6)), f"edge {edge}"
        e = p.edges[edge]
        # frente apunta hacia el interior (misma dirección que la normal)
        assert it.front[0] * e.n[0] + it.front[1] * e.n[1] == pytest.approx(1.0)
        assert it.footprint.distance(p.room.exterior) == pytest.approx(0.0, abs=1e-6)


def test_door_swing_blocked():
    door = {"id": "p", "type": "door", "wall": 0, "offset": 40, "width": 90, "swing": "in", "hinge": "start"}
    blocked = plan([{"id": "a", "size": [40, 40], "at": [100, 60]}], [door])
    free = plan([{"id": "a", "size": [40, 40], "at": [500, 300]}], [door])
    assert "SWING" in codes(blocked)
    assert "SWING" not in codes(free)


def test_opening_blocked_by_item():
    win = {"id": "v", "type": "window", "wall": 2, "offset": 150, "width": 200}
    p = plan([{"id": "a", "size": [120, 50], "wall": {"edge": 2, "offset": 100}}], [win])
    assert "OPENING" in codes(p)


def test_opening_must_fit_in_wall():
    with pytest.raises(PlanError, match="no cabe"):
        plan(openings=[{"id": "p", "type": "door", "wall": 0, "offset": 550, "width": 90}])


def test_narrow_gap_and_narrow_ok():
    items = [
        {"id": "a", "size": [100, 50], "at": [200, 200]},
        {"id": "b", "size": [100, 50], "at": [340, 200]},
    ]
    assert "NARROW" in codes(plan(items, rules={"min_gap": 60}))
    items[1]["narrow_ok"] = True
    assert "NARROW" not in codes(plan(items, rules={"min_gap": 60}))


def test_gap_rules_min_max_and_unmatched_selector():
    items = [
        {"id": "a", "size": [50, 50], "at": [100, 100], "group": "x"},
        {"id": "b", "size": [50, 50], "at": [400, 100]},
    ]
    far = plan(items, rules={"gaps": [{"a": "a", "b": "b", "max": 100}]})
    assert "GAP" in codes(far)
    near = plan(items, rules={"gaps": [{"a": "a", "b": "b", "min": 100}]})
    assert "GAP" not in codes(near)
    miss = plan(items, rules={"gaps": [{"a": "group:nada", "b": "b", "min": 1}]})
    assert any(i.code == "GAP" and i.severity == "warning" for i in validate(miss))


def test_repeat_ids_and_selector_by_base_id():
    p = plan([{"id": "s", "size": [40, 40], "at": [100, 100], "repeat": {"count": 3, "step": [60, 0]}}])
    assert [i.id for i in p.items] == ["s-1", "s-2", "s-3"]
    assert len(p.select("s")) == 3


def test_catalog_use_override_and_unknown():
    cat = {"mesa": {"label": "Mesa", "size": [80, 80], "group": "mesas"}}
    p = plan([{"use": "mesa", "id": "m", "at": [300, 200], "size": [100, 100]}], catalog=cat)
    assert p.items[0].w == 100 and p.items[0].group == "mesas"
    with pytest.raises(PlanError, match="no está en el catálogo"):
        plan([{"use": "nada", "at": [1, 1]}], catalog=cat)


def test_errors_are_clear():
    with pytest.raises(PlanError, match="falta la posición"):
        plan([{"id": "a", "size": [10, 10]}])
    with pytest.raises(PlanError, match="duplicado"):
        plan([{"id": "a", "size": [10, 10], "at": [50, 50]}, {"id": "a", "size": [10, 10], "at": [90, 50]}])
    with pytest.raises(PlanError, match="units"):
        build_plan({"units": "ft", "room": {"width": 1, "depth": 1}})


def test_polygon_room_l_shape():
    room = {"polygon": [[0, 0], [600, 0], [600, 200], [300, 200], [300, 400], [0, 400]]}
    p = plan([{"id": "a", "size": [100, 100], "at": [450, 300]}], room=room)  # en el hueco de la L
    assert "OUTSIDE" in codes(p)


def test_units_meters_and_area():
    p = build_plan({"units": "m", "room": {"width": 6, "depth": 4}})
    assert p.area_m2(p.room.area) == pytest.approx(24.0)


def test_svg_and_dxf_cli_roundtrip(tmp_path: Path):
    src = tmp_path / "p.yaml"
    assert main(["new", str(src)]) == 0
    assert main(["build", str(src), "--strict"]) == 0
    assert (tmp_path / "out" / "p.svg").read_text().startswith("<svg")
    doc = ezdxf.readfile(tmp_path / "out" / "p.dxf")
    assert len(doc.audit().errors) == 0
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {"WALLS", "ITEMS", "DIMENSIONS"} <= layers
    dims = [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]
    assert sorted(round(d.get_measurement()) for d in dims) == [400, 400, 600, 600]


def test_check_exit_code_on_error(tmp_path: Path):
    src = tmp_path / "bad.yaml"
    src.write_text(
        "units: cm\nroom: {width: 300, depth: 300}\nitems:\n"
        "  - {id: a, size: [100,100], at: [150,150]}\n  - {id: b, size: [100,100], at: [180,150]}\n"
    )
    assert main(["check", str(src)]) == 1


def test_install_skill_local_and_force(tmp_path: Path):
    assert main(["install-skill", str(tmp_path)]) == 0
    skill = tmp_path / ".claude" / "skills" / "floorplan-2d"
    assert (skill / "SKILL.md").exists() and (skill / "references" / "format.md").exists()
    assert main(["install-skill", str(tmp_path)]) == 2  # ya existe
    assert main(["install-skill", str(tmp_path), "--force"]) == 0


def test_render_marks_issues():
    p = plan([
        {"id": "a", "size": [100, 100], "at": [300, 200]},
        {"id": "b", "size": [100, 100], "at": [350, 200]},
    ])
    svg = render_svg(p, validate(p))
    assert "#d00000" in svg
