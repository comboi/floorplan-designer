---
name: floorplan-2d
description: Dibuja y valida planos 2D en planta de cualquier espacio (local, oficina, taller, almacén, cocina, sala, vivienda…) a partir de un YAML con recinto, aberturas y objetos con medidas; exporta SVG, PNG y DXF con cotas y comprueba solapes, zonas libres, giro de puertas y pasos estrechos. Úsala cuando pidan una distribución, layout, plano en planta, "colocar/mover/girar" equipos o mobiliario, comprobar pasillos o medidas, o un DXF de la distribución. No es para modelado 3D ni planos de estructura.
---

# floorplan-2d

Un plano es un archivo YAML; el CLI `floorplan` lo valida y lo dibuja. Tú editas el YAML y regeneras: así cada cambio ("mueve la mesa", "gira el armario") es una línea.

Esta skill es **genérica**: no sabe nada del tipo de espacio. Las reglas de oficio (pasillos, distancias, ergonomía) las pone el usuario en `rules` y en `clearance` de cada objeto, o las dice en la conversación.

## Flujo

1. **Reúne los datos mínimos.** Recinto (largo × ancho o vértices), unidades, dónde están puertas y ventanas, y la lista de objetos con medidas. Si faltan medidas, pregunta lo imprescindible o propón valores de catálogo y dilo.
2. **Escribe o edita el YAML.** `floorplan new <ruta>.yaml` crea una plantilla y un `catalog.yaml`; de ahí partes.
3. **Construye:** `floorplan build <plan>.yaml` (SVG + DXF por defecto, `-f png` para PNG). Sale en `out/` junto al plan.
4. **Mira el resultado** (lee el PNG/SVG) y **cuenta los avisos al usuario** en palabras claras ("el armario queda a 55 cm del mostrador; pediste 80").
5. **Itera:** cambia el YAML y repite. Para solo validar: `floorplan check <plan>.yaml` (`--json` para procesarlo).

Comprueba siempre `floorplan check` antes de dar un plano por bueno. Un plano con `[ERROR]` no está terminado salvo que el usuario acepte la incidencia.

## Convenciones (imprescindibles)

- **Y hacia arriba (norte).** Origen del recinto en (0, 0), esquina suroeste.
- **Bordes del recinto** numerados en el orden de los vértices. En un rectángulo: `0` sur (izq→der), `1` este, `2` norte (der→izq), `3` oeste.
- **Un objeto** tiene `size: [ancho, fondo]`. Su **frente** es el lado +y local (con `rotate: 0` mira al norte). `rotate` gira en grados antihorarios alrededor de su centro. En el dibujo, la marca corta del borde indica el frente.
- **Posición:** `at: [x, y]` (centro; `anchor: bl` para esquina inferior-izquierda) **o** `wall: {edge, offset, gap, align}` para pegarlo a un muro, ya orientado con el frente hacia el interior.
- **Aberturas:** `wall` (borde), `offset` (desde el inicio del borde), `width`. Puertas con `swing: in|out|none` y `hinge: start|end`.
- **`clearance`** = zona libre que el objeto necesita: un número (frente) o `{front, back, left, right, all}`. Se dibuja punteada y se valida.

Formato completo con ejemplos: [references/format.md](references/format.md).

## Qué valida

| Código | Significa |
|---|---|
| `OUTSIDE` | un objeto sobresale del recinto |
| `OVERLAP` | dos objetos se solapan (permite `overlap_ok: true`) |
| `CLEARANCE` | algo invade la zona libre de un objeto, o esa zona sale del recinto |
| `SWING` | un objeto obstruye el giro de una puerta |
| `OPENING` | un objeto bloquea el hueco de una puerta o ventana |
| `NARROW` | paso menor que `rules.min_gap` entre objetos o con un muro (`narrow_ok: true` lo omite, p. ej. sillas) |
| `GAP` | incumple una regla `rules.gaps` (`min`/`max` entre selectores) |

`ERROR` hace fallar `check` (salida 1). `aviso` informa.

## Reglas para trabajar bien

- **Unidades:** pregunta o deduce y fíjalas en `units`. Por defecto `cm`. No mezcles.
- **No inventes medidas de equipos concretos.** Usa el catálogo para piezas genéricas y pide la medida real (ficha técnica) cuando importe. Marca lo supuesto.
- **Un cambio, una regeneración.** No reescribas el plano entero para mover un objeto.
- **Ids estables.** Nombra los objetos con ids cortos y reutilízalos: facilitan las reglas `gaps` y las referencias del usuario.
- **Catálogo propio por proyecto.** Si el usuario repite piezas, añádelas a su `catalog.yaml`; el del paquete es solo de ejemplo (`floorplan catalog`).
- **Normativa:** los mínimos que pongas en `rules` son criterios del usuario o recomendaciones generales, no cumplimiento de ninguna norma. Si piden verificar normativa (accesibilidad, incendios, sanitaria), dilo claramente: eso lo confirma un técnico competente.
- **DXF:** se exporta en las mismas unidades del plano (`$INSUNITS` declarado), con capas `WALLS`, `OPENINGS`, `ITEMS`, `ITEMS-TEXT`, `CLEARANCE`, `DIMENSIONS`.

## Instalación (si `floorplan` no existe)

```bash
uv tool install "/ruta/al/paquete/floorplan-2d[png]"
floorplan install-skill          # en la carpeta del workspace
```
