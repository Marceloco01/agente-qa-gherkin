"""
Tests de application/seguimiento/patrones_criterios_v2.py.

Fijan el arreglo del 2026-09-20 descrito dentro de `contar_criterios`: una HU
con criterios `[C1]` y `[C2]` que, dentro de cada contexto, lista campos de
pantalla más cortos que el largo mínimo debe contar 2 criterios, no cero.

Los textos son sintéticos: reproducen la ESTRUCTURA del caso real sin copiar
la descripción de Jira, para que el repositorio público no lleve datos de la
organización.
"""

from application.seguimiento.patrones_criterios_v2 import contar_criterios


HU_CORCHETES_CON_VINETAS_CORTAS = """Yo como
Usuario de prueba
Necesito
Recalcular un dato en el paso 3
Para
agilizar el registro
Criterios de Aceptación:
[C1]
Contexto: Estando en la pantalla del paso 3 Evento: al cargar por primera vez estos datos:
- Campo uno
- Campo dos
- Campo tres
Resultado: se muestra un botón para calcular y un valor calculado por defecto

[C2]
Contexto: Estando en la pantalla del paso 3 Evento: al cambiar alguno de estos datos:
- Campo uno
- Campo dos
- Campo tres
Resultado:
- aparece un mensaje que pide volver a calcular el valor
- se deshabilita el botón guardar hasta que se vuelva a calcular
"""


class TestEtiquetasEntreCorchetesConVinetasCortas:
    def test_cuenta_los_dos_criterios(self):
        patron, criterios = contar_criterios(HU_CORCHETES_CON_VINETAS_CORTAS)
        assert patron == "etiqueta_por_posicion"
        assert len(criterios) == 2

    def test_cada_criterio_llega_hasta_la_etiqueta_siguiente(self):
        _, criterios = contar_criterios(HU_CORCHETES_CON_VINETAS_CORTAS)
        assert "calcular" in criterios[0]
        assert "guardar" not in criterios[0]
        assert "guardar" in criterios[1]

    def test_en_crudo_las_vinetas_cortas_son_las_que_matchean_primero(self):


        patron, crudos = contar_criterios(HU_CORCHETES_CON_VINETAS_CORTAS, largo_minimo=0)
        assert patron == "vinetas_en_seccion"
        assert len(crudos) == 6


class TestSinCriteriosUtilizables:
    def test_solo_vinetas_cortas_queda_en_cero(self):


        texto = "Criterios de Aceptación:\n- Campo uno\n- Campo dos\n- Campo tres\n"
        patron, criterios = contar_criterios(texto)
        assert patron == "vinetas_en_seccion"
        assert criterios == []
