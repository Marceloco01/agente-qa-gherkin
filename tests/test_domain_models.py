"""Tests para domain/models.py."""

from domain.models import HistoriaUsuario, TestCase


class TestHistoriaUsuario:
    def test_descripcion_vacia_es_pobre(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="")
        assert hu.descripcion_es_pobre is True

    def test_descripcion_corta_es_pobre(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="muy corta")
        assert hu.descripcion_es_pobre is True

    def test_descripcion_con_solo_espacios_es_pobre(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="   ")
        assert hu.descripcion_es_pobre is True

    def test_descripcion_de_50_caracteres_exactos_no_es_pobre(self):

        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="x" * 50)
        assert hu.descripcion_es_pobre is False

    def test_descripcion_de_49_caracteres_es_pobre(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="x" * 49)
        assert hu.descripcion_es_pobre is True

    def test_descripcion_larga_no_es_pobre(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="x" * 200)
        assert hu.descripcion_es_pobre is False

    def test_test_plan_key_es_none_por_defecto(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="x" * 100)
        assert hu.test_plan_key is None


class TestTestCase:
    def test_str_incluye_key_titulo_y_gherkin(self):
        tc = TestCase(titulo="Login exitoso", gherkin="Scenario: Login exitoso", hu_key="PROJ-1")
        texto = str(tc)
        assert "PROJ-1" in texto
        assert "Login exitoso" in texto
        assert "Scenario:" in texto
