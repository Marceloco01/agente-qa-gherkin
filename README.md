# Agente de IA para diseño de pruebas de software

Sistema que genera casos de prueba en formato Gherkin a partir de historias de
usuario de Jira, los somete a revisión humana y los publica en Xray vinculados
al Test Plan correspondiente. Incorpora recuperación aumentada (RAG) sobre el
histórico de casos del equipo, verificación de alucinación y un conjunto de
tableros que miden el efecto del agente sobre el proceso de pruebas.

La inferencia corre de forma local sobre Ollama (`llama3.1:8b`). No se envían
datos a servicios externos de modelos.

---

## Versión del paquete

Versión funcional de referencia: **v1.0.2**. Esta edición de distribución incorpora ajustes posteriores de limpieza y anonimización documentados en el CHANGELOG; no es una copia histórica exacta de la v1.0.2.

El script `scripts/armar_registros_con_keys.py` se incluye únicamente para el análisis exploratorio retrospectivo. No pertenece al flujo operativo de Vera y Gio.

## Alcance inicial y evolución

Cronología declarada por el responsable del proyecto (pendiente de corroboración con respaldos o registros contemporáneos):

| Hito | Fecha |
|---|---|
| Inicio del desarrollo inicial | 11/07/2026 |
| Entrega funcional declarada de Vera y Gio | 02/08/2026 |
| Inicio declarado del uso operativo | 03/08/2026 |

| Componente | Alcance inicial declarado | Evolución posterior |
|---|---|---|
| Arquitectura e integración Jira/Xray | Integración funcional | Mantenimiento |
| Acceso | Acceso mediante credenciales | Evolución de autenticación; decisión de login fechada 01/09/2026 |
| Vera | Evaluación de HU y puntuación de calidad | Mejoras funcionales, incluidas las decisiones fechadas 28/08/2026 sobre umbral y dependencia visual |
| Gio | Generación Gherkin, RAG, verificación de alucinaciones, revisión humana y publicación | Correcciones de seguridad y control documentadas en v1.0.2 (26/11/2026) |
| Métricas, dashboards, Nexus Insights y reportes estadísticos | Fuera del alcance inicial declarado | Ampliaciones posteriores |

Vera y Gio comparten un flujo de trabajo, pero una modificación de Vera no implica necesariamente una modificación de la generación de Gio. La ejecución de las pruebas corresponde al analista QA, no al agente. Según el responsable del proyecto, los casos aprobados del flujo operativo se cargaron en Xray y fueron ejecutados por QA. Esta declaración se distingue del corpus exploratorio procesado sin publicación mediante `RepositoryNulo`.

### Conciliación de fechas técnicas

| Registro del código | Fecha registrada | Alcance verificable |
|---|---|---|
| Migración `0c951ffe71f7` | 29/06/2026 | Esquema inicial de persistencia, anterior al inicio declarado del desarrollo. |
| Migración `0a0210e50b09` | 30/06/2026 | Campos de detección de alucinaciones, anteriores al inicio declarado. |
| Migración `d4f28a91e6c3` | 28/08/2026 | Incorporación de columnas de persistencia de evaluaciones de Vera y fecha de fin de proceso. |
| `application/validar_hu.py` | 28/08/2026 | Decisiones documentadas sobre umbral configurable, bloqueo y persistencia. |

Las fechas de junio podrían corresponder a preparación previa, pero el paquete no permite confirmarlo. La migración de agosto acredita una ampliación del esquema; no establece por sí sola la fecha de primera disponibilidad de Vera. La existencia de una versión operativa antes del post-test requiere evidencia contemporánea. El ZIP no incluye el repositorio `.git` ni un historial de commits verificable.

El paquete actual no contiene una versión histórica del 02/08 que permita comprobar la disponibilidad de cada componente en esa fecha. Las migraciones, las decisiones fechadas y el historial de cambios se conservan. El acceso mediante credenciales configuradas y el login como puerta de acceso son mecanismos distintos. La ejecución humana de casos históricos debe acreditarse mediante trazas Jira/Xray; los análisis exploratorios no constituyen evidencia de ejecución.

---

## Arquitectura

Arquitectura hexagonal (puertos y adaptadores). La regla que la sostiene es una
sola: **las dependencias apuntan hacia adentro**. El diseño busca que el dominio y los casos de uso dependan de interfaces,
aunque existen dependencias directas hacia adaptadores e infraestructura en algunos casos de uso.

| Capa | Carpeta | Responsabilidad |
|---|---|---|
| Dominio | `domain/` | Entidades y reglas propias del problema. Sin dependencias externas. |
| Puertos | `ports/` | Contratos que el núcleo necesita del exterior. |
| Casos de uso | `application/` | Orquestación. Acá vive todo el cálculo. |
| Adaptadores | `adapters/` | Implementaciones concretas de cada puerto. |
| Infraestructura | `infrastructure/` | Configuración, base de datos, migraciones, generación de reportes. |
| Interfaz | `frontend/` | Streamlit. Declarativa: no calcula indicadores. |

Dos consecuencias prácticas de este diseño:

- **Sustituir un proveedor de LLM es escribir un adaptador.** El resto del
  sistema depende de `ports/llm_provider.py`, nunca de una implementación.
  `infrastructure/fabrica_llm.py` es el único punto donde se resuelve cuál se
  usa.
- **Las pantallas no calculan.** Los indicadores se computan en
  `application/` y viajan resueltos hacia la vista. Esto evita la clase de
  error en que un tablero muestra un agregado obtenido sobre un conjunto
  distinto del que dice mostrar.

### Puertos definidos

| Puerto | Qué abstrae | Adaptador incluido |
|---|---|---|
| `issue_tracker` | Lectura y escritura de incidencias | Jira Cloud |
| `test_management` | Gestión de casos y planes de prueba | Xray Cloud |
| `llm_provider` | Inferencia y embeddings | Ollama |
| `repository` | Persistencia del flujo operativo | SQLAlchemy / PostgreSQL |
| `vector_store` | Búsqueda por similitud | pgvector |
| `tesis_repository` | Corpus del estudio comparativo | CSV |
| `resultados_documento` | Resultados por ciclo de prueba | CSV |

---

## Estructura

```
agente_qa/
├── domain/              Entidades y reglas de negocio
├── ports/               Contratos (interfaces abstractas)
├── application/         Casos de uso
│   ├── seguimiento/     Motor de métricas por historia
│   ├── tesis/           Cálculo de los indicadores del estudio
│   └── impacto/         Análisis comparativo agente vs. histórico
├── adapters/            Implementaciones de los puertos
│   ├── issue_tracker/   Jira Cloud, Xray Cloud
│   ├── llm/             Ollama
│   ├── repository/      SQLAlchemy
│   ├── vector_store/    pgvector
│   └── tesis/           Lectura del corpus
├── infrastructure/      Configuración, base de datos, reportes
│   ├── db/              Modelos ORM y migraciones Alembic
│   └── reportes/        Construcción de los libros de resultados
├── frontend/            Aplicación Streamlit
│   ├── pages/           Pantallas
│   └── comun/           Estilo institucional y gráficos SVG
├── scripts/             Extracción, ETL y generación de reportes
└── tests/               Pruebas unitarias y verificación de pantallas
```

---

## Puesta en marcha

### Requisitos

- Python 3.13
- PostgreSQL 16 o superior con la extensión `pgvector`
- Ollama con los modelos `llama3.1:8b` y `nomic-embed-text`

### Instalación

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

# requirements-lock.txt fija las versiones exactas con las que el sistema
# fue verificado. Es el que se instala. `requirements.txt` solo declara las
# dependencias sin versión, para regenerar el lock cuando corresponda.
pip install -r requirements-lock.txt

copy env.example .env          # Windows
# cp env.example .env          # Linux / macOS
```

Completar `.env` con las credenciales de Jira y Xray y la contraseña de la
base de datos. **El archivo `.env` no se versiona** (ver `.gitignore`).

### Modelos de IA

Con Ollama instalado y en ejecución, descargar los modelos requeridos:

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
ollama list
```

Configurar `OLLAMA_HOST` si el servicio no está en el equipo local.

### Base de datos

```bash
alembic upgrade head
```

### Ejecución

```bash
streamlit run frontend/streamlit_app.py
```

Para despliegue con Docker, ver `DESPLIEGUE.md`.

---

## Pruebas

```bash
pytest tests/
```

Las pruebas cubren los casos de uso, los adaptadores de Jira y Xray, y el
proveedor de LLM, todos contra dobles de prueba: ninguna requiere red ni
credenciales.

`tests/verificar_pagina_resultados_documento.py` es una verificación aparte.
Ejecuta una pantalla completa contra un Streamlit simulado y compara cada
indicador, celda por celda, contra la fuente de resultados publicada. Sirve
para detectar la discrepancia entre lo que el tablero muestra y lo que la
fuente dice, que es un error silencioso y difícil de ver a ojo.

```bash
python tests/verificar_pagina_resultados_documento.py
```

---

## Reproducir los resultados del artículo

**Desde la Hoja de datos 1 (material suplementario del artículo).** Es la vía
para quien lee el artículo: copie el archivo como `datos/hoja_datos_1.csv` y
ejecute un solo comando, sin SPSS y sin conexión a Jira ni Xray:

```bash
python scripts/analisis_estadistico.py --hoja datos/hoja_datos_1.csv --verificar
```

Debe terminar con "las 190 cifras publicadas coinciden con el cálculo". Para
validar la hoja sin recalcular nada:
`python scripts/construir_hoja_datos.py --hoja datos/hoja_datos_1.csv`.

**Desde la exportación de la organización (solo los autores).** Así se
construyó la Hoja de datos 1, en dos pasos:

```bash
# 1. Construir y validar la Hoja de datos 1 (formato largo: una fila por
#    ciclo y periodo, códigos CP1..CP60 y PT1..PT60).
python scripts/construir_hoja_datos.py \
    --tabla-ancha resultados_documento_60ciclos.csv \
    --marcas marcas_sensibilidad.csv \
    --salida datos/hoja_datos_1.csv

# 2. Calcular todas las pruebas y compararlas con las cifras publicadas.
python scripts/analisis_estadistico.py --hoja datos/hoja_datos_1.csv --verificar
```

- `resultados_documento_60ciclos.csv` es la exportación de las hojas "Datos
  pre" y "Datos post" del libro de resultados, consolidado a partir de las
  exportaciones de Jira y Xray. No se publica (información de la organización);
  la Hoja de datos 1 anonimizada sí, como material suplementario.
- `marcas_sensibilidad.csv` (columnas `periodo,ciclo,marca`; plantilla en
  `scripts/marcas_sensibilidad_plantilla.csv`, con los ciclos del pre-test ya
  cargados y los 14 del post-test por completar) declara por qué se
  excluye cada ciclo en los análisis A, B y C. Las marcas válidas y la regla de
  cada análisis están en `application/tesis/hoja_datos.py`.
- `analisis_estadistico.py` escribe `resultados_estadisticos.json` y
  `resultados_estadisticos.md`. Con `--verificar` compara cada una de las
  cifras de `scripts/valores_articulo.json` contra el cálculo y termina con
  error si alguna no coincide.

**Diseño:** el pre-test y el post-test tienen ciclos distintos (muestras
independientes). Se usa la U de Mann-Whitney (como SPSS: sin corrección por
continuidad y con corrección por empates), r = |Z|/√N, Fisher exacta,
IC 95 % de Newcombe y Bonferroni (α = 0.05/3). Los p de Mann-Whitney se
reportan como en el artículo, calculados con el Z redondeado a tres decimales
que muestra SPSS; el JSON de salida guarda también el p con el Z completo
(solo cambia el tercer decimal del estado de defectos en el análisis A: 0.531
frente a 0.530). El cálculo está en
`application/tesis/estadistica.py`, sin dependencias externas; Shapiro-Wilk
se calcula solo si `scipy` está instalado.

**Análisis exploratorios que no forman parte del artículo.** La pantalla
"Pre-Test / Post-Test" y `scripts/generar_reportes_indicadores.py` comparan el
proceso manual con lo que NEXUS *habría* hecho sobre las mismas historias
(análisis retrospectivo). Sus cifras son distintas de las del artículo y no
deben citarse como resultados del estudio.

**Análisis complementarios (v1.0.2).** Responden a la revisión del artículo
y no cambian las Tablas 4 a 7:

```bash
python scripts/analisis_ajustado.py --hoja datos/hoja_datos_1.csv            # principal
python scripts/analisis_ajustado.py --hoja datos/hoja_datos_1.csv --analisis B
```

Cobertura con modelo cuasi-binomial ajustado por log(casos especificados),
ejecuciones con modelo cuasi-binomial y defectos por caso con modelo
cuasi-Poisson con *offset* log(casos). Para la segunda evaluación ciega de la
cobertura: `--plantilla-kappa criterios.csv` genera la plantilla con los
ciclos barajados y sin periodo, y `--kappa plantilla_completada.csv` calcula
el kappa de Cohen.

**Diseño exploratorio de septiembre.** Ver
`docs/DISENO_EXPLORATORIO_SEPTIEMBRE.md`: explica qué módulos pertenecen al
análisis retrospectivo previo y qué falta para documentar la trazabilidad del
post-test (Hoja de datos 3).

**Dos definiciones de "estado de defectos" en el código.** Solo una
corresponde al artículo:

| Dónde | Cómo se calcula | Uso |
|---|---|---|
| `CalcularResultadosDocumento` (`application/tesis/calcular_resultados_documento.py`) y `application/tesis/analisis_articulo.py` | Defectos corregidos / defectos detectados en cada periodo, solo en ciclos con al menos un defecto | **La del artículo** (Tablas 5 a 7) |
| `CalcularMetricasTesis` (`application/tesis/calcular_metricas_tesis.py`) | Cuenta como corregido (mitigado) el defecto cuyo veredicto humano es "Evitable", es decir, uno que el agente *habría* prevenido | Análisis exploratorio contrafáctico; **no se publicó** |

`CalcularMetricasTesis` alimenta la pantalla "Pre-Test / Post-Test" y
`scripts/generar_reportes_indicadores.py`.

---

## Archivos de datos

Los únicos archivos de datos incluidos están en `datos/` y son anonimizados:
la **Hoja de datos 1** (tabla por ciclo de las Tablas 4 a 7) y la **Hoja de
datos 3** (trazabilidad en Jira y Xray de PT1-PT60). Los demás archivos del
corpus (exportaciones de Jira y Xray, CSV y libros de cálculo internos) no se
incluyen, por tratarse de información de un entorno productivo.

Las pantallas que dependen de un archivo ausente lo informan en pantalla en
lugar de fallar. Las que operan contra Jira, Xray y PostgreSQL funcionan con
normalidad una vez configuradas las credenciales.
