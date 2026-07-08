# Configuración del caso de estudio

Define **qué** trazamos y **con qué prioridades**. A diferencia de `data/raw/` y `data/processed/`, esta carpeta **sí se versiona**: es pequeña y describe el escenario de forma reproducible.

- [`escenario.yaml`](escenario.yaml) — CRS y rejilla de trabajo, AOI, origen y destino.
- [`perfiles.yaml`](perfiles.yaml) — perfiles de prioridad: vectores de pesos que producen rutas diferenciadas.

> Cambiar el escenario o los perfiles cambia las rutas y la comparativa, no el código. Mantener aquí los valores del caso que se presente.
