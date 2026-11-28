"""Pruebas de application/tesis/estadistica.py.

Los valores de referencia se obtuvieron con scipy 1.x (mannwhitneyu sin
corrección por continuidad, fisher_exact) y, para Newcombe, son los intervalos
publicados en el artículo.
"""

import pytest

from application.tesis.estadistica import (
    bisagras_tukey,
    describir,
    fisher_exacta,
    mann_whitney,
    newcombe,
    p_desde_z_publicado,
    wilson,
)


class TestMannWhitney:
    def test_sin_empates(self):
        r = mann_whitney([1, 2, 3], [4, 5, 6])
        assert r.u == 0.0
        assert r.w == 6.0
        assert r.z == pytest.approx(-1.963961, abs=1e-6)
        assert r.p == pytest.approx(0.049535, abs=1e-6)
        assert r.r == pytest.approx(0.801784, abs=1e-6)

    def test_con_empates_como_spss(self):
        r = mann_whitney([0, 50, 100, 100, 75, 100], [100, 100, 100, 90, 100, 100, 87.5])
        assert r.u == 13.5
        assert r.rango_promedio_1 == pytest.approx(5.75)
        assert r.rango_promedio_2 == pytest.approx(8.071429, abs=1e-6)
        assert r.p == pytest.approx(0.221853, abs=1e-6)
        assert r.z < 0


        assert r.p_articulo == pytest.approx(p_desde_z_publicado(r.z))
        assert round(p_desde_z_publicado(-0.62743), 3) == 0.531

    def test_u_es_el_menor_y_simetrico(self):
        a, b = [3, 5, 7, 9], [1, 2, 4]
        r1, r2 = mann_whitney(a, b), mann_whitney(b, a)
        assert r1.u == r2.u
        assert r1.p == pytest.approx(r2.p)

    def test_todo_empatado(self):
        r = mann_whitney([100, 100], [100, 100, 100])
        assert (r.z, r.p) == (0.0, 1.0)

    def test_grupo_vacio(self):
        with pytest.raises(ValueError):
            mann_whitney([], [1])


class TestFisher:
    def test_valor_de_referencia(self):
        assert fisher_exacta(59, 1, 41, 19) == pytest.approx(8.613060725455579e-06, rel=1e-9)

    def test_tabla_pequena(self):
        assert fisher_exacta(3, 1, 1, 3) == pytest.approx(0.485714, abs=1e-6)

    def test_sin_diferencia(self):
        assert fisher_exacta(5, 5, 5, 5) == pytest.approx(1.0)


class TestProporciones:
    def test_wilson_contiene_la_proporcion(self):
        li, ls = wilson(41, 60)
        assert li < 41 / 60 < ls

    @pytest.mark.parametrize("x1,x2,esperado", [
        (59, 41, (30.0, 17.4, 42.6)),
        (51, 31, (33.3, 16.9, 47.5)),
    ])
    def test_newcombe_reproduce_el_articulo(self, x1, x2, esperado):
        d, li, ls = newcombe(x1, 60, x2, 60)
        assert tuple(round(100 * v, 1) for v in (d, li, ls)) == esperado


class TestDescriptivos:
    def test_bisagras_n_par(self):
        assert bisagras_tukey([1, 2, 3, 4, 5, 6, 7, 8]) == (2.5, 4.5, 6.5)

    def test_bisagras_n_impar_incluye_la_mediana(self):
        assert bisagras_tukey([1, 2, 3, 4, 5, 6, 7]) == (2.5, 4, 5.5)

    def test_describir(self):
        d = describir([0.0, 100.0, 100.0, 100.0])
        assert d.media == 75.0
        assert d.mediana == 100.0
        assert d.de == pytest.approx(50.0)
