# Memoria de trabajo

Este documento recoge la trazabilidad de las tareas realizadas en el proyecto, los avances, las decisiones técnicas y el registro de cambios principales.

## Objetivo

Mantener un historial sencillo y accesible de qué se ha hecho, cuándo y por qué, para facilitar la coordinación del equipo y la revisión posterior.

## Registro de actividades

### Semana 1
- Lectura del enunciado del reto y conceptos clave (GIS, LCP, coste multicriterio)
- Formación en QGIS

### Semana 2 
- Reunión con los contactos de Enagás
- **Hito 1 en proceso:**
    -   Origen: planta de hidrógeno de Puertollano (38.68151749377432, -4.049492223656498)
    -   Punto final: norte de Puertollano (38.80681007796324, -4.028723916034112)
    -   Fuentes catalogadas: ver `data/raw/FUENTES.md`
    -   Capas reproyectadas a EPSG:25830 (de momento falta el rural) → ver `data/processed/` 
    -   Distinguir entre ficheros tipo .gpkg () y tipo .tif () y fuardárlos respectivamente en 'data/processed/Recorte_AOI' y 'data/processed/Rasters_AOI'
- **Hito 2 inicio:**
    -Elaborar prompts del hito 2 para semana 3
- Creación de `memoria.md` para la trazabilidad del trabajo.

### Plan para Semana 3
- Detectar vacíos (hito 1) y comprobar que el AOI se ha realizado correctamente. Estamos a la espera de Claude Pro para ello.
- Avanzar con hito 2 usando el prompt generado en semana 2


