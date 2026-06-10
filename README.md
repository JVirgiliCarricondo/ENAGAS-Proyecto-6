# CI2 Lab 2026 · Grupo 6 — Diseño de ramales (Enagás)

**Generación automatizada de trazados de ramales de H₂.**

Workspace del Grupo 6 del CI2 Lab 2026 (Cátedra de Industria Inteligente, ETSI-ICAI · Comillas). Aquí conviven las tres dimensiones del trabajo del grupo: la **formación** de los alumnos, la **coordinación y seguimiento** del proyecto, y el **desarrollo del código** del prototipo.

## Por dónde empezar

| Si eres… | Empieza por |
|----------|-------------|
| Alumno nuevo en el grupo | [`docs/reto6_enagas.md`](docs/reto6_enagas.md) → [`formacion/plan_formativo.md`](formacion/plan_formativo.md) |
| Quieres ver el plan y el avance | [`coordinacion/plan_proyecto.md`](coordinacion/plan_proyecto.md) y [`estado.md`](estado.md) |
| Vas a programar | [`proyecto/README.md`](proyecto/README.md) y [`proyecto/arquitectura.md`](proyecto/arquitectura.md) |
| Coordinación / contexto del lab | [`CLAUDE.md`](CLAUDE.md) |

## El reto en una frase

Dado un **origen** (planta de H₂) y un **destino** (conexión a red troncal), la herramienta genera **3-5 trazados alternativos diferenciados** sobre **GIS público** y los compara por **longitud, coste relativo (índice, no €), cruces especiales, km en zona protegida, km en zona urbana y pendiente**. El objetivo es **comparar alternativas para decidir**, no entregar una única ruta "óptima" ni estimar costes en euros.

## Estructura

```
.
├── CLAUDE.md            # contexto del workspace
├── estado.md           # resumen ejecutivo del avance
├── docs/               # contexto compartido + análisis técnico del reto
├── formacion/          # plan y materiales de formación
├── coordinacion/       # plan de proyecto, sprints, seguimiento, equipo
└── proyecto/           # el prototipo (código, datos, pruebas)
```
