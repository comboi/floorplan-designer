# Formato del plano (YAML)

Todo es opcional salvo `room` y lo que cada bloque exige.

## Cabecera y recinto

```yaml
name: Mi plano
units: cm            # mm | cm | m
room:
  width: 600         # rectángulo…
  depth: 400
  # …o polígono (en sentido horario o antihorario, sin cruzarse):
  # polygon: [[0,0],[600,0],[600,300],[400,400],[0,400]]
  origin: [0, 0]     # desplaza todo el recinto (opcional)
  wall_thickness: 20 # grosor del muro hacia fuera; por defecto 20 cm
```

Los bordes se numeran según el orden de los vértices. Rectángulo: 0 sur, 1 este, 2 norte, 3 oeste.

## Aberturas

```yaml
openings:
  - { id: puerta, type: door,    wall: 0, offset: 40,  width: 90, swing: in,  hinge: start }
  - { id: ventana, type: window, wall: 2, offset: 150, width: 200 }
  - { id: paso,   type: opening, wall: 1, offset: 100, width: 120 }   # hueco sin hoja
```

- `offset`: distancia desde el inicio (vértice) del borde. Debe caber: `offset + width ≤ longitud del borde`.
- `swing`: `in` (hacia dentro), `out`, `none`. `hinge`: `start` o `end` (lado de la bisagra mirando el borde).
- Una puerta con `swing: in/out` valida que el abanico esté libre (`SWING`). Todas las aberturas exigen una franja libre delante (`OPENING`).

## Objetos

```yaml
items:
  - id: mesa
    label: Mesa de trabajo      # texto del plano (por defecto, el id)
    size: [180, 70]             # ancho (x local) × fondo (y local); el frente es +y
    at: [300, 200]              # centro; anchor: bl → esquina inferior-izquierda
    rotate: 90                  # grados antihorarios
    group: trabajo              # agrupa para colores y reglas
    clearance: { front: 90, left: 30 }   # o un número = solo frente; all = anillo completo
    color: "#ffd166"            # opcional
    overlap_ok: false           # true: no se valida solape (alfombras, zonas dibujadas)
    narrow_ok: false            # true: no avisa de paso estrecho (sillas pegadas a mesas)
```

Círculo: `shape: circle` con `diameter: 90` (o `size: [90, 90]`).

### Pegado a un muro

```yaml
  - id: armario
    size: [120, 50]
    wall: { edge: 2, offset: 20, gap: 0, align: start }   # align: start | center | end
```

Queda apoyado en el borde, con el frente hacia el interior. `offset` se mide desde el inicio del borde (o desde el final si `align: end`); `gap` separa del muro.

### Repetir

```yaml
  - { use: silla, id: silla, at: [100, 135], repeat: { count: 4, step: [60, 0] } }
  # con `wall`, step es un número (separación a lo largo del muro)
```

Ids resultantes: `silla-1`, `silla-2`… El id base `silla` sirve de selector para todas.

## Catálogo

```yaml
catalog: catalog.yaml     # archivo, lista de archivos, o mapa en línea
```

```yaml
# catalog.yaml
mesa-4: { label: Mesa 4p, size: [80, 80], group: mesas }
```

`use: mesa-4` hereda la definición; lo que escribas en el objeto la sobrescribe. Un `use` inexistente da error con la lista de piezas disponibles. `floorplan catalog` muestra el catálogo de ejemplo.

## Reglas

```yaml
rules:
  min_gap: 90                      # paso mínimo entre objetos y con los muros → aviso NARROW
  gaps:
    - { a: group:sillas, b: mesa, max: 60 }     # cada silla a ≤ 60 de la mesa más cercana
    - { a: fregadero, b: frigorifico, min: 50 } # separación mínima
```

Selectores: `id`, `id:x` (id o id base de un `repeat`) o `group:x`. Una regla sin coincidencias avisa (`GAP`), no se ignora en silencio.
`min` exige distancia ≥ min a **todos** los objetos de `b`; `max` exige que el **más cercano** esté a ≤ max. Distancias entre contornos (no entre centros).

## Salidas

| Comando | Genera |
|---|---|
| `floorplan build plan.yaml` | `out/plan.svg`, `out/plan.dxf` |
| `floorplan build plan.yaml -f png` | además `out/plan.png` (requiere el extra `[png]`) |
| `--no-zones` `--no-dims` `--no-labels` | oculta zonas libres, cotas o etiquetas |
| `--strict` | salida 1 si hay errores (útil en scripts) |
| `floorplan check plan.yaml [--json]` | solo validación |

Rojo = error, ámbar = aviso, naranja punteado = zona libre. Las cotas del recinto van por fuera del muro.
