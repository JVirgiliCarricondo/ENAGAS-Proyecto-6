# CI2 Lab 2026 — Retos para los equipos

**8ª edición · 25 de mayo – 17 de julio de 2026 · ETSI-ICAI / IIT**

Este documento describe los **10 retos** que las empresas patrono y la propia Cátedra de Industria Inteligente proponen para esta edición del CI2 Lab. Lee con calma todos los enunciados antes de votar tus preferencias en el cuestionario de MS Forms.

## Sobre el programa

- **Duración:** 8 semanas, de lunes a viernes en jornada de mañana.
- **Equipos:** 3-4 personas por reto, asignados por la Cátedra cruzando perfil técnico y preferencias del cuestionario.
- **Sistema de votación:** cada alumno reparte 3 puntos a su reto preferido, 2 puntos al segundo y 1 punto al tercero. Las tres elecciones deben ser distintas.
- **Asignación final:** la decide la Cátedra teniendo en cuenta tu votación, tu encaje técnico con cada reto y las restricciones de cada equipo.

## Logística de presencia

| Reto | Presencia |
|------|-----------|
| Endesa | ICAI (5 días) |
| Horse (los 3 retos) | 3 días en oficinas de Horse en **Valladolid** + 2 días en ICAI · *viajes financiados por la Cátedra* |
| Enagás (los 2 retos) | 3 días en oficinas de Enagás + 2 días en ICAI |
| Kearney — Digital Model Factory | IIT (espacio físico de la DMF) |
| Repsol | 3 días en oficinas de Repsol + 2 días en ICAI |
| CII (los 2 retos internos) | ICAI |

---

## Reto 1 — Endesa: Agente Copilot Studio + SharePoint para especificaciones de transformadores

**Empresa:** Endesa. **Ubicación:** ICAI.

**Descripción.** Construir un agente conversacional con **Microsoft Copilot Studio + SharePoint** que gestione una base de datos de **especificaciones de transformadores**. El resultado se integrará en los sistemas de información de Endesa para mejorar sus procesos de back-office (consulta por especificación técnica, validación de fichas, generación de comparativas, etc.).

**Stack tecnológico:** MS Copilot Studio, SharePoint, integración Teams / portales internos de Endesa.

**Qué aprenderás.** Diseño de agentes conversacionales sobre la pila Microsoft, modelado de bases de conocimiento en SharePoint, integración de soluciones de IA en sistemas corporativos reales.

---

## Retos 2 a 4 — Horse: tres líneas de analítica avanzada en planta

**Empresa:** Horse (grupo automoción). **Ubicación:** **3 días en oficinas de Horse en Valladolid + 2 días en ICAI · viajes financiados por la Cátedra**.

Horse propone tres retos complementarios, ordenados de menor a mayor riesgo tecnológico. Cada uno lo aborda **un grupo independiente de 2-3 alumnos**. Stack común: Python (pandas, sklearn, SHAP); entorno cloud opcional. Entregable: notebook documentado + presentación tipo mini-consultoría.

### Reto 2 — Explainable Manufacturing en cloud

Pipeline analítico en cloud (p.ej. GCP + Vertex AI) que prediga desviaciones del **Rendimiento Operacional (RO)** **y** explique de forma interpretable qué variables están detrás de las pérdidas (temperaturas, tiempos de ciclo, presión, etc.). El foco está en la **explicabilidad operativa** (XAI/SHAP), no en construir el modelo más exacto posible.

**Stack:** Random Forest / XGBoost, SHAP, dashboards (Looker / notebooks), GCP + Vertex AI opcional.

### Reto 3 — Reduced-Order Models PIML para inyección de aluminio

Modelo reducido (*surrogate model*) que aproxime el comportamiento de la **inyección de aluminio** (llenado, defectos potenciales) combinando datos reales con principios físicos — enfoque **Physics-Informed Machine Learning**. Es el primer paso de la línea estratégica de IA física en Horse.

**Stack:** red neuronal simple o GPR con restricciones físicas (monotonicidad, límites); datos reales + simulaciones simplificadas. Camino de continuidad: PINNs, integración con CFD, optimización de parámetros de proceso.

### Reto 4 — Cross-Process Analytics: inyección vs estanqueidad

Análisis cruzado entre parámetros de **inyección** y resultados de **ensayos de estanqueidad** para detectar relaciones causales indirectas entre proceso y calidad final. Objetivo industrial: romper silos entre procesos.

**Stack:** integración de datasets (matching inyección ↔ test estanqueidad), análisis exploratorio multivariable (correlaciones, clustering, PCA), modelado predictivo (clasificación OK/NOK), feature importance.

---

## Retos 5 y 6 — Enagás: dos retos sobre normativa y trazados

**Empresa:** Enagás (sistema gasista, hidrógeno verde). **Ubicación:** 3 días en oficinas de Enagás + 2 días en ICAI.

### Reto 5 — Asistente de Consulta Comparativa ES vs EU (calidad del gas)

Prototipo que responda preguntas comparativas sobre **3 parámetros de calidad del gas (O₂, H₂S, PCS)** entre la **normativa española** (RD 919/2006 + Resolución BOE) y el **Network Code INT/CAM UE**. Debe dar **trazabilidad al texto original** y avisar explícitamente cuando los valores **no son comparables sin normalización** (p.ej. "10 ppm molar" en España vs. "10 ppm vol" en Alemania son distintos si no se normalizan unidades y condiciones de referencia).

**Arquitectura híbrida** (clave del reto): ontología determinista estructurada de los 3 parámetros + extracción de valores normativos de PDFs públicos + RAG sobre los PDFs para preguntas en lenguaje natural + capa de comparación que consulta la mini-ontología y devuelve respuesta con flag de comparabilidad.

**Stack:** LLMs, RAG, bases de datos vectoriales, ontologías.

### Reto 6 — Generación automatizada de trazados (H₂)

Dado un punto de origen (planta de H₂) y un destino (conexión a red troncal), la herramienta genera automáticamente **3-5 trazados alternativos diferenciados** sobre **GIS público** (DEM Copernicus, Corine Land Cover, OSM, hidrografía IGN, Red Natura 2000, mapa geológico IGME) y los presenta en **comparativa multi-criterio**: longitud, coste *relativo* (índice, no €), nº y tipo de cruces especiales, km en zona protegida, km en zona urbana/periurbana, pendiente máxima y media.

El énfasis está en el **problema de selección y comparación de trazados**, no en estimar costes absolutos.

**Stack:** GIS público, algoritmos de camino de mínimo coste con perfiles de prioridad distintos (para producir rutas diferenciadas, no variaciones del mismo corredor), raster multicriterio.

---

## Reto 7 — Kearney: Digital Model Factory

**Empresa:** Kearney (la Cátedra inaugura la iniciativa en junio). **Ubicación:** IIT (espacio físico de la DMF).

**Descripción.** Por iniciativa de Kearney, la Cátedra inaugura en junio la **Digital Model Factory**: un espacio donde una serie de **proveedores tecnológicos instalan demostradores** y que está llamado a ser **punto de encuentro entre empresas tecnológicas, industriales, alumnos e investigadores**. El equipo del CI2 Lab asignado a este reto trabajará en el **desarrollo y puesta a punto de los demostradores** que los proveedores instalen.

**Stack:** variable por demostrador (se cierra a medida que se confirmen los proveedores).

**Qué aprenderás.** Trabajo con proveedores tecnológicos reales, integración y puesta a punto de demostradores industriales, exposición directa a empresas tecnológicas e industriales que visiten el espacio.

---

## Reto 8 — Repsol: Centro de Competencia en IA Generativa (IA Agéntica)

**Empresa:** Repsol. **Ubicación:** 3 días en oficinas de Repsol + 2 días en ICAI.

**Descripción.** Colaboración directa con el **Centro de Competencia en IA Generativa** de Repsol para trabajar sobre sus **desarrollos internos de IA Agéntica**. Es continuidad natural del reto Repsol del CI2 Lab 2025 ("Metodología de implementación de sistemas de IA agénticos — evaluación de LLMs con MLflow"): el conocimiento generado el año pasado se extiende este año hacia las líneas activas del CC IA Generativa.

**Stack:** frameworks de agentes, modelos y stack de infraestructura del CC IA Generativa (detalle a cerrar con Repsol).

**Qué aprenderás.** Cómo se construye y opera una capacidad agéntica dentro de una gran empresa energética, integración con sistemas productivos reales, exposición al ecosistema de un Centro de Competencia.

---

## Retos 9 y 10 — Proyectos internos de la Cátedra

**Promotor:** Cátedra de Industria Inteligente (CII). **Ubicación:** ICAI.

### Reto 9 — IA agéntica abierta multi-modelo

Desarrollo de un **modelo de IA agéntica abierto, en línea con propuestas tipo Open Code**, en el que se puedan **configurar los distintos modelos que realizan la inferencia en función del tipo de tarea requerida en cada momento de la ejecución**. La idea es que el agente no se case con un único LLM, sino que enrute cada paso a un modelo distinto según la naturaleza del paso (razonamiento profundo, generación de código, síntesis, llamada a herramientas, etc.).

**Líneas de trabajo:**

- Diseño del esquema de configuración (qué modelo se invoca para qué tipo de tarea).
- Capa de orquestación que aplica el routing entre modelos.
- Conjunto de tareas de referencia para evaluar comparativamente el comportamiento.
- Componentes abiertos / interoperables.

### Reto 10 — Ingeniero informático artificial con Claude Code

Desarrollo de un **"ingeniero informático artificial"** construido sobre **Claude Code** que cubra dos funciones complementarias:

1. **Resolución de problemas en proyectos de computación de altas prestaciones (HPC)** — soporte automático a desarrolladores e investigadores que trabajan sobre clusters HPC (depuración, paralelización, build issues, scripts de envío de jobs, etc.).
2. **Detección, centralización e inventariado de las herramientas software** presentes en los distintos proyectos de la Cátedra — escanear los repositorios y entregables de la CII para identificar qué herramientas, librerías y servicios están en uso, agruparlos y mantener un inventario consultable.

**Líneas de trabajo:**

- Adaptación de Claude Code a flujos típicos de HPC (entornos modulados, gestores de colas, depuración remota).
- Sistema de escaneo automático de proyectos para extraer dependencias y herramientas.
- Centralización del inventario e interfaz de consulta.
- Caso de uso real con uno o varios proyectos vivos de la Cátedra como banco de pruebas.

---

## Calendario clave

- **25 de mayo (lun)** — Sesión inaugural: presentación de retos y apertura de votaciones.
- **27 de mayo (mié)** — Cierre de votación **a las 10:00**; al final de la jornada se comunica la asignación de alumnos a retos.
- **1 de junio (lun)** — Comienzo del trabajo en los retos.
- **Semana 1 (25–29 may)** — Formación intensiva: *campus de vibe coding*. (Detalle en presentación específica.)
- **Junio (fecha por confirmar)** — Inauguración de la Digital Model Factory en el IIT.
- **17 de julio (vie)** — Cierre del programa, presentación de resultados.

## Cómo se vota

1. Abre el cuestionario de MS Forms que recibirás por email.
2. Marca tu **1ª opción (3 puntos)**, **2ª opción (2 puntos)** y **3ª opción (1 punto)**. Las tres deben ser **retos distintos**.
3. Envía. Solo se admite una respuesta por persona.

**Plazo:** miércoles **27 de mayo de 2026 a las 10:00**. La asignación a retos se comunica al final de la jornada de ese mismo día.

Cualquier duda sobre los enunciados, escribe a **Álvaro López López** ([allopez@comillas.edu](mailto:allopez@comillas.edu)) y a la cuenta de la Cátedra ([catedrai2@comillas.edu](mailto:catedrai2@comillas.edu)).
