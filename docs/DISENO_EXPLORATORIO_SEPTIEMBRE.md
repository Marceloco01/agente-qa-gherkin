# Diseño exploratorio de septiembre de 2026 y diseño del artículo

Este documento existe para que nadie confunda dos análisis distintos que
conviven en el código. El responsable del proyecto declara que, en el flujo
operativo, los casos aprobados se cargaron en Xray y fueron ejecutados por QA.
Las citas históricas de la sección 1 describen la corrida exploratoria, no
constituyen una afirmación sobre todo el uso operativo. La trazabilidad de
las ejecuciones del artículo sigue requiriendo los registros correspondientes.

## 1. Análisis retrospectivo exploratorio (septiembre de 2026)

Módulos: `infrastructure/reportes/pretest_posttest.py`,
`infrastructure/reportes/registro_pretest.py`,
`application/tesis/calcular_metricas_tesis.py`,
`scripts/armar_registros_con_keys.py` y la pantalla "Pre-Test / Post-Test".

Lo que dicen sus propios comentarios fechados:

| Fecha | Archivo | Contenido |
|---|---|---|
| 06/09/2026 | `pretest_posttest.py` | Corpus de 43 HU; el post-test era la salida del agente sobre esas mismas HU; "los casos del agente nunca se subieron ni se ejecutaron". |
| 16/09/2026 | `calcular_metricas_tesis.py` | "Índice de ejecuciones" medía ejecutabilidad estructural del guion; el estado de defectos post era un conjunto de defectos "mitigados". |
| 20/09/2026 | `armar_registros_con_keys.py` | Una versión previa del registro completaba la muestra con 13 filas simuladas (SIM-xx); 20 HU cerradas entre el 10/08 y el 11/09 tenían ejecuciones en curso. |
| 14/10/2026 | `frontend/streamlit_app.py` | Primera mención del diseño de 60 ciclos de prueba. |

## 2. Diseño del artículo (60 ciclos pre-test frente a 60 post-test)

Módulos: `application/tesis/hoja_datos.py`, `application/tesis/analisis_articulo.py`,
`application/tesis/estadistica.py`, `application/tesis/modelos_ajustados.py`,
`scripts/construir_hoja_datos.py`, `scripts/analisis_estadistico.py`,
`scripts/analisis_ajustado.py` y la pantalla "Resultados".

## 3. Trazabilidad del post-test (Hoja de datos 3)

`datos/hoja_datos_3.xlsx` (y `.csv`) reúne, para PT1-PT60, la historia, el
plan de pruebas, los casos, la ejecución y las corridas, con sus fechas,
tomadas de las exportaciones de Jira y Xray Cloud (27 y 28/11/2026) y
anonimizadas. Lo que muestran:

- 60 planes, 605 casos de tipo Cucumber y 60 ejecuciones. Por ciclo, los casos
  especificados y ejecutados coinciden con la Hoja de datos 1.
- Planes, casos y ejecuciones se crearon entre el 03/08 y el 10/09/2026
  (fechas de creación de Jira, no editables); en cada plan, todos los casos se
  crearon en el mismo minuto.
- Los 605 casos figuran creados por la cuenta de servicio de Jira a la que
  pertenece la credencial de la API de Xray que usa el agente (`XRAY_CLIENT_ID`,
  según la configuración de API Keys de Xray), no por la analista.
- Las corridas se registraron entre el 03/08 y el 11/09/2026: 604 en PASSED y
  1 sin ejecutar.
