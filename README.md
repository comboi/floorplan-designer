# floorplan-2d

Planos 2D en planta **genéricos** a partir de un archivo YAML. Sin reglas de ningún tipo de local: un recinto, aberturas y objetos con medidas. Valida (solapes, zonas libres, giro de puertas, pasos estrechos) y exporta **SVG, PNG y DXF** desde la misma geometría. Incluye una skill para Claude Code que se instala en cada workspace.

## Instalar

### Requisitos

- Python 3.10 o superior
- [uv](https://docs.astral.sh/uv/) (recomendado): `curl -LsSf https://astral.sh/uv/install.sh | sh` o `brew install uv`
- Acceso a `github.com` y a PyPI (si tu red usa un registro corporativo, usa el público para esta instalación)

### Opción recomendada: comando global con uv

```bash
uv tool install "floorplan-2d[png] @ git+https://github.com/comboi/floorplan-designer"
```

Queda disponible el comando `floorplan` en cualquier carpeta. El extra `[png]` añade `resvg-py` para exportar PNG; sin él solo se generan SVG y DXF.

Si `floorplan` no se encuentra, añade el directorio de binarios de uv al PATH:

```bash
uv tool update-shell     # y abre una terminal nueva
```

### Otras opciones

```bash
# sin instalar, ejecución puntual
uvx --from "floorplan-2d[png] @ git+https://github.com/comboi/floorplan-designer" floorplan --version

# con pip en un entorno virtual
pip install "floorplan-2d[png] @ git+https://github.com/comboi/floorplan-designer"

# desde una copia local (para desarrollar)
git clone https://github.com/comboi/floorplan-designer.git
cd floorplan-designer
uv tool install ".[png]"          # o: uv pip install -e ".[dev,png]"
```

### Comprobar la instalación

```bash
floorplan --version               # floorplan-2d 0.1.0
floorplan new /tmp/demo/plan.yaml && floorplan build /tmp/demo/plan.yaml -f png
```

### Actualizar y desinstalar

```bash
uv tool install --force --reinstall "floorplan-2d[png] @ git+https://github.com/comboi/floorplan-designer"
floorplan install-skill --force   # en cada workspace, para refrescar la copia de la skill

uv tool uninstall floorplan-2d
```

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
