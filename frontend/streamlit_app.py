"""
Punto de entrada real de la app -- lo que corre `streamlit run
frontend/streamlit_app.py`. Este archivo es SOLO el router.

**Reestructuración 2026-09-16 (arquitectura definida por el usuario).** El
menú pasó de 9 secciones heredadas a 7, con un criterio explícito: la
navegación prioriza el trabajo real con la IA, no la narrativa de la tesis.
La tesis tiene su propia sección en vez de ordenar toda la barra lateral.

Qué cambió y por qué, decidido con el usuario:

1. **`pages/1_📊_Dashboard.py` se partió.** Concentraba 1.208 líneas con dos
   cosas distintas adentro: los indicadores del AGENTE (calidad de la
   generación, evaluación de Vera, desenlace de alucinaciones) y los del
   EQUIPO QA (volumen, defectos por severidad, detalle por HU). Ahora son
   `12_🤖_Indicadores_IA.py` y `13_🎯_Indicadores_QA.py`, con lo compartido
   en `frontend/comun/panel_operativo.py`.
2. **`pages/5_🎯_Seguimiento.py` se fusionó.** Su "Resumen del período" y su
   "Detalle por HU" mostraban lo MISMO que el Dashboard. Lo único propio
   --la evolución histórica por cohortes-- se absorbió en Indicadores de QA.
3. **El bloque "Interpretación con IA" (Nora) se cayó.** El propio Dashboard
   lo tenía marcado como deprecado y absorbido por Nexus Insights.
4. **`pages/6_🌱_Adopción_IA.py` salió del menú.** Sin función definida que
   aporte al producto.
5. **"Resumen ejecutivo" es página nueva** (`14_📋_Resumen_Ejecutivo.py`):
   los cuatro indicadores con su Δ y los principales resultados. El detalle
   quedó en `8_🧪_Pre_Test_Post_Test.py`, al lado, en la misma sección.
6. **"Validar evitabilidad" y "Revisar cobertura" no se escondieron en una
   sección "Herramientas".** Son parte de la evaluación: la primera va con
   la tesis (evaluación de defectos), la segunda con impacto de la IA
   (cobertura IA vs humano).

Los archivos viejos (`1_📊_Dashboard.py`, `5_🎯_Seguimiento.py`,
`6_🌱_Adopción_IA.py`) siguen en disco pero FUERA del router: no hay permiso
de borrado en la carpeta conectada, y renombrar implica crear+borrar. Se
borran a mano cuando se quiera; mientras tanto no aparecen en el menú.

Importante -- con `st.navigation()` Streamlit deja de descubrir `pages/`
automáticamente: esta lista es la ÚNICA fuente de verdad del menú. Una
página nueva que no se sume acá no aparece. Cada página sigue llamando a su
propio `st.set_page_config(...)` para el título de la pestaña del navegador;
lo que se controla acá es el nombre en la barra lateral y el agrupamiento.

El aspecto de la barra lateral --gris pizarra, bordes por pestaña, sin emojis-- lo
pone `frontend/comun/estilo.py`, no este archivo: acá solo viven los nombres.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

pagina_activa = st.navigation(
    {


        "Trabajar con IA": [
            st.Page("vista_trabajar_con_ia.py", title="Generar casos", default=True),
        ],
        "Inicio": [
            st.Page("pages/0_🏠_Inicio.py", title="Command Center"),
        ],

        "Evaluación del agente": [


            st.Page("pages/15_📈_Resultados.py", title="Resultados"),
            st.Page("pages/8_🧪_Pre_Test_Post_Test.py", title="Pre-Test / Post-Test"),


            st.Page("pages/9_✅_Validar_Evitabilidad.py", title="Revisar defectos"),
        ],

        "Impacto de la IA": [
            st.Page("pages/10_🔍_Revisar_Cobertura.py", title="Cobertura IA vs Humano"),
            st.Page("pages/4_⏱️_Revisión_Retrospectiva.py", title="Revisión retrospectiva"),
            st.Page("pages/3_🏆_Gio_vs_Historico.py", title="Cobertura de Gio vs Histórico"),
        ],

        "Calidad Operativa": [
            st.Page("pages/12_🤖_Indicadores_IA.py", title="Indicadores de IA"),
            st.Page("pages/13_🎯_Indicadores_QA.py", title="Indicadores de QA"),
        ],
        "NEXUS Insights": [
            st.Page("pages/7_💬_Nexus_Insights.py", title="Chat analítico"),
        ],
        "Configuración": [
            st.Page("pages/2_⚙️_Configuracion.py", title="Credenciales"),
        ],
    }
)
pagina_activa.run()
