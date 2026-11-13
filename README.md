# floorplan-2d

Planos 2D en planta **genéricos** a partir de un archivo YAML. Sin reglas de ningún tipo de local: un recinto, aberturas y objetos con medidas. Valida (solapes, zonas libres, giro de puertas, pasos estrechos) y exporta **SVG, PNG y DXF** desde la misma geometría. Incluye una skill para Claude Code que se instala en cada workspace.

## Instalar

```bash
# desde GitHub, con uv (recomendado): queda como comando global `floorplan`
uv tool install "floorplan-2d[png] @ git+https://github.com/comboi/floorplan-designer"
# (sin el extra [png] no se exporta PNG, solo SVG y DXF)

# o desde una copia local
uv tool install "/ruta/a/floorplan-designer[png]"

# o en un entorno virtual
pip install "/ruta/a/floorplan-designer[png]"
```

Actualizar: repite el `uv tool install` con `--force --reinstall`.

## Usar en un workspace

```bash
cd mi-workspace
floorplan install-skill            # copia la skill a .claude/skills/floorplan-2d
floorplan new planos/local.yaml    # plan.yaml + catalog.yaml de ejemplo
floorplan build planos/local.yaml  # valida y genera planos/out/local.svg y .dxf
floorplan build planos/local.yaml -f png
floorplan check planos/local.yaml  # solo validar (salida 1 si hay errores)
```

`floorplan install-skill --global` la deja en `~/.claude/skills` (disponible en todos los workspaces).

## Formato del plano

```yaml
name: Sala de ejemplo
units: cm                      # mm | cm | m
room: { width: 600, depth: 400, wall_thickness: 20 }   # o polygon: [[x,y], …]
catalog: catalog.yaml          # opcional
openings:
  - { id: puerta, type: door, wall: 0, offset: 40, width: 90, swing: in, hinge: start }
  - { id: ventana, type: window, wall: 2, offset: 150, width: 200 }
rules:
  min_gap: 80                  # paso mínimo → aviso NARROW
  gaps: [ { a: group:sillas, b: mesa, max: 60 } ]
items:
  - { use: mesa-4, id: mesa, at: [150, 200] }
  - { id: armario, size: [120, 50], wall: { edge: 2, align: center }, clearance: { front: 80 } }
```

Referencia completa en `src/floorplan2d/skill/references/format.md` (se copia con la skill).

## Pruebas

```bash
uv pip install -e ".[dev,png]" && pytest
```

## Licencia

MIT.
