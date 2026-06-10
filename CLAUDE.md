# CI2 Lab 2026 — Grupo 6 (Reto 6, Enagás): Generación automatizada de trazados de ramales de H₂

> Workspace de **coordinación, seguimiento y análisis técnico** del Grupo 6 del CI2 Lab 2026.
> Contexto general de la iniciativa en [`docs/Descripcion_CI2_Lab.md`](docs/Descripcion_CI2_Lab.md).
> Enunciado completo de todos los retos en [`docs/retos_alumnos.md`](docs/retos_alumnos.md).

## Qué es este proyecto

El CI2 Lab es el programa de verano de la **Cátedra de Industria Inteligente** (ETSI-ICAI, Comillas). En su 8ª edición (25 may – 17 jul 2026), equipos de 3-4 estudiantes resuelven retos reales de las empresas patrono.

Este workspace acompaña al **Grupo 6**, que resuelve el **Reto 6 propuesto por Enagás**:

> **Generación automatizada de trazados de ramales de H₂.** Dado un **punto de origen** (planta de H₂) y un **destino** (conexión a red troncal), una herramienta genera automáticamente **3-5 trazados alternativos diferenciados** sobre **GIS público** y los presenta en **comparativa multi-criterio**: longitud, coste *relativo* (índice, **no €**), nº y tipo de cruces especiales, km en zona protegida, km en zona urbana/periurbana, pendiente máxima y media. El énfasis está en el **problema de selección y comparación de trazados**, no en estimar costes absolutos.

Desglose técnico detallado del reto en [`docs/reto6_enagas.md`](docs/reto6_enagas.md).

## Las tres dimensiones de trabajo

Este workspace se organiza en torno a las tres dimensiones del acompañamiento al grupo:

1. **Formación** — [`formacion/`](formacion/CLAUDE.md): plan formativo y materiales para que los alumnos adquieran las habilidades técnicas necesarias (Python geoespacial, CRS y alineación de rasters, superficies de coste, camino de mínimo coste, diferenciación de rutas, visualización geoespacial).
2. **Coordinación y seguimiento** — [`coordinacion/`](coordinacion/CLAUDE.md): plan de proyecto, WBS, sprints semanales, seguimiento del avance, equipo y reuniones.
3. **Desarrollo del código** — [`proyecto/`](proyecto/CLAUDE.md): el prototipo en sí. Pipeline geoespacial (ingesta + superficies de coste + motor LCP + métricas + comparación), código, datos y pruebas.

## Estado

El resumen ejecutivo del avance está en [`estado.md`](estado.md). Actualizarlo al cierre de cada sprint semanal.

## Calendario del programa (Grupo 6)

- **25–29 may** — Semana 0: formación intensiva (*campus de vibe coding*).
- **27 may 10:00** — Cierre de votación; asignación de alumnos a retos.
- **1 jun** — Comienzo del trabajo en el reto.
- **Presencia semanal:** 3 días en oficinas de Enagás + 2 días en ICAI.
- **17 jul** — Cierre del programa y presentación de resultados.

Detalle de hitos y sprints en [`coordinacion/plan_proyecto.md`](coordinacion/plan_proyecto.md).

## Contactos

| Rol | Nombre | Email |
|-----|--------|-------|
| Investigador principal / coordinador | Álvaro López López | allopez@comillas.edu |
| Investigadora cátedra | Lucía Guita López | — |
| Cuenta de la Cátedra | CII | catedrai2@comillas.edu |
| Enagás | Susana de Pablo | spablo@enagas.es |
| Enagás | Pedro del Castillo | pedelcastillo@enagas.es |

## Estructura de carpetas

- [`CLAUDE.md`](CLAUDE.md) — este fichero: contexto y árbol del workspace.
- [`estado.md`](estado.md) — resumen ejecutivo del avance.
- [`docs/`](docs/) — contexto compartido y análisis técnico del reto.
- [`formacion/`](formacion/) — dimensión 1: plan y materiales de formación.
- [`coordinacion/`](coordinacion/) — dimensión 2: gestión del proyecto y seguimiento.
- [`proyecto/`](proyecto/) — dimensión 3: el prototipo (código, datos, pruebas).

## Convenciones

- **Idioma:** documentación y comunicación en español; código y nombres de variables en inglés.
- **Alinear antes de comparar:** ninguna capa GIS entra en el pipeline sin estar reproyectada al **CRS común (EPSG:25830)** y remuestreada a la **rejilla común**. Es el corazón del reto: si las capas no están alineadas, los costes mienten.
- **Rutas demostrablemente diferenciadas:** las 3-5 rutas deben ser alternativas reales, no variaciones del mismo corredor con ruido.
- **Coste relativo, nunca €:** todo coste es un **índice normalizado**; el sistema no estima costes económicos absolutos.
