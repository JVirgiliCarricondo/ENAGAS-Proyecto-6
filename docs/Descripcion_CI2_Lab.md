# CI2 Lab 2026 — Coordinacion

> Topic del hub [`000_GESTIONES_IA/`](../CLAUDE.md). Para la estructura general, arbol de topics e infraestructura compartida (`tools/`, `emails_entrada/`, `emails_salida/`) ver el [CLAUDE.md raiz](../CLAUDE.md).

## Que es el CI2 Lab

El CI2 Lab (CIC LAB Investigacion) es un programa de la **Catedra de Industria Inteligente** de la Escuela Tecnica Superior de Ingenieria (ETSI-ICAI) de la Universidad Pontificia Comillas. Funciona desde 2019 y en 2026 celebra su **octava edicion**.

Las empresas patrono de la catedra plantean **retos reales** que equipos de estudiantes resuelven durante un programa intensivo de verano. Los estudiantes participan mediante un sistema de becas, dedicando ~25 horas semanales a investigacion y desarrollo.

### Formato

- **Duracion:** 8 semanas, de lunes a viernes de 9:00 a 14:00
- **Inicio edicion 2026:** lunes 25 de mayo de 2026
- **Fin estimado:** viernes 17 de julio de 2026
- Equipos de 3-4 estudiantes por reto
- Los alumnos pueden visitar las instalaciones de las empresas

### Investigadores principales

- **Alvaro Lopez Lopez** — investigador principal de CI2 Comillas ICAI y creador de la iniciativa
- **Lucia Guita Lopez** — investigadora en la catedra y profesora en ICAI

## Estado

El resumen ejecutivo con el estado de cada subtopic esta en [`estado.md`](estado.md). Mantenerlo al dia cada vez que avance un subtopic.

## Subtopics

- **[`call_for_challenges/`](call_for_challenges/CLAUDE.md)** — Solicitud, recogida y cierre de retos con las empresas patrono. Fecha limite 15/05/2026.
- **[`alumnos_candidatos/`](alumnos_candidatos/CLAUDE.md)** — Recepcion, filtrado y asignacion de alumnos a los retos. Asignacion antes del 25/05/2026.

> Cuando se incorpore un nuevo subtopic, anadir una linea aqui y una seccion en [`estado.md`](estado.md).

## Empresas patrono y contactos (edicion 2026)

| Empresa | Contacto | Email |
|---------|----------|-------|
| **Acerinox** | Fernando del Pino | fernando.delpino@acerinox.com |
| | Antonio Gayo | antonio.gayo@acerinox.com |
| **Enagas** | Susana de Pablo | spablo@enagas.es |
| | Pedro del Castillo | pedelcastillo@enagas.es |
| **Pladur** | David Linares | david.linares@pladur.com |
| **Repsol** | Juan Manuel Garcia | jmgarciagar@repsol.com |
| **Endesa** | Alicia Mateo | alicia.mateo@enel.com |
| | Maria Avery | maria.avery@enel.com |
| | Manuel Rodriguez | manuel.rodriguezdc@endesa.es |
| **Kearney** | Nicolas Sanz | nicolas.sanzernest@kearney.com |
| | Isabel Morillo | isabel.morillo@kearney.com |
| **Horse** | Alberto de los Ojos | alberto.de-los-ojos@horse.tech |
| | Maria Jesus Esbec | maria-jesus.esbec-alonso@horse.tech |

## Proyectos de la edicion 2025 (referencia)

Estos fueron los 8 retos abordados en la edicion anterior (7a, verano 2025). Son utiles como referencia para el tipo de retos que se solicitan a los patronos:

1. **Antolin** — Herramienta semi-automatica para analisis de nuevos mercados (scraper + IA para generar informes sobre el sector del automovil por region)
2. **Endesa** — Mapa de tensiones y tecnologias de la red de distribucion europea (impacto de la prohibicion del SF6)
3. **Gestamp** — Analitica de datos en procesos de soldadura (deteccion de defectos con ML en Databricks)
4. **Kearney** — Digital Model Factory (DMF) (catalogo de casos de uso de tecnologias industriales 4.0)
5. **Pladur** — Algoritmo para ubicacion de airbags en cubicaje de contenedores (optimizacion logistica 3D)
6. **Repsol** — Metodologia de implementacion de sistemas de IA agenticos (evaluacion de LLMs con MLflow)

Empresas que participaron en 2025 pero no aparecen en la lista de contactos 2026: Antolin, Gestamp.
Empresas nuevas en 2026 respecto a 2025: Acerinox, Enagas, Horse.

## Estructura de carpetas del topic

- [`CLAUDE.md`](CLAUDE.md) — este fichero, contexto y arbol de subtopics.
- [`estado.md`](estado.md) — resumen ejecutivo con el estado de cada subtopic.
- [`call_for_challenges/`](call_for_challenges/) — subtopic: retos con patronos.
- [`alumnos_candidatos/`](alumnos_candidatos/) — subtopic: alumnos candidatos.
- `CIC_Lab_2025.pdf` — memoria anual 2025 con los proyectos de la edicion anterior (referencia, compartida entre subtopics).

> Los scripts (`tools/`) y el flujo de emails (`emails_entrada/`, `emails_salida/`) viven en la [raiz del hub](../CLAUDE.md#infraestructura-compartida), no dentro de este topic.
