# Cambios

## Ajustes posteriores de distribución — 2026-11-27

Limpieza del paquete y del vocabulario interno. No cambia ningún cálculo.

- **Logs fuera del paquete.** Las pruebas escriben el log en una carpeta
  temporal (`tests/conftest.py`, variable `AGENTE_QA_DIR_LOGS` en
  `infrastructure/config.py`). Antes, cada corrida de pytest llenaba
  `logs/agente_qa.log` con datos de prueba y ese archivo terminó dentro del
  zip de la v1.0.2. `logs/` sigue en el `.gitignore`: los logs son datos de
  ejecución y no se distribuyen con el código fuente.
- **Rótulo interno reemplazado.** El nombre interno de una etapa del plan de
  trabajo pasa a "análisis retrospectivo" en comentarios y textos, y a
  `retro` en nombres de archivo e identificadores (32 archivos editados,
  7 renombrados; p. ej.
  `scripts/calcular_cobertura_real_retro.py`,
  `application/seguimiento/corpus_retro.py`,
  `frontend/pages/3_🏆_Gio_vs_Historico.py`). En los módulos del análisis
  exploratorio de septiembre este es el único cambio: ningún comentario
  fechado se modificó ni se eliminó.
- Se corrigió un resto de anonimización en `scripts/armar_registros_con_keys.py`
  ("(, 2026-09-20)").
- 179 pruebas (la v1.0.2 también tenía 179; el CHANGELOG anterior decía 178).

## v1.0.2 — 2026-11-26

Correcciones derivadas de la revisión del artículo. No cambian ninguna cifra
de las Tablas 4 a 7 (`analisis_estadistico.py --verificar` sigue dando 190/190).

- **Falla segura en la verificación de alucinaciones**
  (`application/generar_casos.py`, `application/revisar_test_case.py`).
  Si el verificador falla o no devuelve resultado para un caso, el caso queda
  marcado (`DETALLE_VERIFICACION_NO_DISPONIBLE`) y no puede aprobarse sin
  edición o regeneración. Hasta la v1.0.1 pasaba sin marca (al generar) o
  conservaba el estado previo (al regenerar). `GenerarCasos` expone
  `verificaciones_no_disponibles`.
- **Bloqueo de aprobación en el caso de uso.** `RevisarTestCase.aprobar()`
  lanza `AprobacionBloqueadaError` si el caso está marcado; antes el bloqueo
  solo existía en la interfaz. La edición manual sigue siendo la vía de
  validación humana, como describe el artículo (la edición limpia la marca
  sin una nueva verificación automática; queda registrado en
  `alucinacion_detectada_alguna_vez`).
- **Umbral de Vera registrado.** Nueva columna `vera_umbral_aplicado`
  (migración `a5d1c0e2f9b3`), que guarda el umbral vigente en cada
  evaluación. Evita que se repita un cambio de umbral sin rastro, como el del
  lote de septiembre.
- **Análisis complementarios** (`application/tesis/modelos_ajustados.py`,
  `scripts/analisis_ajustado.py`): cobertura ajustada por log(casos
  especificados) y defectos por caso con modelos cuasi-binomial y
  cuasi-Poisson (IRLS con numpy, sin dependencias nuevas); kappa de Cohen y
  plantilla ciega para un segundo evaluador de cobertura.
- **Transparencia del diseño.** Aviso en los módulos del análisis
  exploratorio de septiembre y `docs/DISENO_EXPLORATORIO_SEPTIEMBRE.md`; los
  módulos se conservan sin cambios de contenido.
- `docs/plantilla_trazabilidad_postest.csv` para la Hoja de datos 3
  (trazabilidad Jira/Xray de PT1-PT60).
- 13 pruebas nuevas (`tests/test_falla_segura_v102.py`,
  `tests/test_modelos_ajustados.py`); 178 en total.

## v1.0.1 — 2026-11-25

Reproducibilidad de los resultados del artículo.

- Nuevo `scripts/construir_hoja_datos.py`: construye y valida la Hoja de datos 1
  (formato largo, códigos anónimos CPn/PTn, marcas de los análisis de
  sensibilidad A, B y C).
- Nuevo `scripts/analisis_estadistico.py`: reproduce las Tablas 4 a 7 (U de
  Mann-Whitney, r, Fisher exacta, IC de Newcombe, Bonferroni) y, con
  `--verificar`, compara cada cifra publicada (`scripts/valores_articulo.json`).
- Nuevos módulos `application/tesis/estadistica.py`, `hoja_datos.py` y
  `analisis_articulo.py`, con 33 pruebas nuevas (166 en total).
- Diseño corregido en el código: el pre-test y el post-test son muestras
  independientes. Se eliminó la descripción "pareada / Wilcoxon" de
  `ports/resultados_documento.py`; las curvas de la pantalla de Resultados son
  ahora curvas de cuantiles (cada periodo ordenado por su cuenta).
- La pantalla "Pre-Test / Post-Test" y `generar_reportes_indicadores.py` quedan
  rotuladas como análisis retrospectivo exploratorio, distinto del artículo.
- Anonimización: se reemplazaron las claves reales de proyectos de Jira en
  comentarios y ejemplos por códigos PRJ-nn.
- Los p de Mann-Whitney se reportan como en el artículo (Z con tres decimales,
  como lo muestra SPSS); `p` con el Z completo se conserva en el JSON.
- El gráfico de la pantalla de Resultados queda solo como `curva_cuantiles` (se quitó el nombre anterior).
- Anonimización: se reemplazaron las claves que quedaban en
  `application/seguimiento/motor.py` (carpeta que el `.gitignore` excluye de las
  búsquedas, aunque el archivo sí es parte del código).
- Anonimización: los dos ejemplos de historias de usuario del prompt de Vera
  se generalizaron (rol y tipos de campaña); instrucciones y criterios sin cambios.
- Paleta neutra: el color de acento de la interfaz y de los gráficos pasa a
  gris pizarra (`#334155`).
- README: se aclaran las dos definiciones de "estado de defectos" que hay en
  el código (la del artículo y la exploratoria).

## v1.0.0 — 2026-11-24

Versión del código usada en el estudio.
