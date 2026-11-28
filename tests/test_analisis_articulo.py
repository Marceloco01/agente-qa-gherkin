"""Pruebas del cálculo de resultados del artículo y de los dos scripts."""

import json
import sys
from pathlib import Path

import pytest

from application.tesis.analisis_articulo import calcular
from application.tesis.hoja_datos import SEVERIDADES, Ciclo, escribir_hoja

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import analisis_estadistico
import construir_hoja_datos


def _ciclo(periodo, n, ejec, espec, cub, ident, det=0, corr=0, marcas=()):
    sev_det = {s: 0 for s in SEVERIDADES}
    sev_corr = {s: 0 for s in SEVERIDADES}
    sev_det["critico"], sev_corr["critico"] = det, corr
    return Ciclo(periodo=periodo, ciclo=f"{'CP' if periodo == 'pre' else 'PT'}{n}",
                 situaciones_identificadas=ident, situaciones_cubiertas=cub,
                 casos_especificados=espec, casos_ejecutados=ejec,
                 defectos_detectados=det, defectos_corregidos=corr,
                 detectados_por_severidad=sev_det, corregidos_por_severidad=sev_corr,
                 marcas=frozenset(marcas))


@pytest.fixture
def ciclos():
    pre = [
        _ciclo("pre", 1, 0, 8, 2, 4, det=2, corr=1, marcas={"sin_ejecuciones"}),
        _ciclo("pre", 2, 8, 8, 4, 4, det=1, corr=1),
        _ciclo("pre", 3, 5, 10, 3, 4, marcas={"ejecuciones_no_vinculadas"}),
        _ciclo("pre", 4, 6, 6, 4, 4),
    ]
    post = [
        _ciclo("post", 1, 10, 10, 4, 4, det=1, corr=1),
        _ciclo("post", 2, 9, 10, 5, 5),
        _ciclo("post", 3, 12, 12, 3, 4, marcas={"umbral_vera_reducido"}),
        _ciclo("post", 4, 10, 10, 4, 4),
    ]
    return pre + post


def test_indices_del_periodo_son_sumas_de_numeradores_y_denominadores(ciclos):
    r = calcular(ciclos)["principal"]["ejecuciones"]
    assert (r["pre"]["numerador"], r["pre"]["denominador"]) == (19, 32)
    assert r["pre"]["indice"] == pytest.approx(100 * 19 / 32)
    assert r["post"]["ciclos_al_100"] == 3
    assert r["ciclos_al_100"]["pre"] == 2


def test_estado_de_defectos_solo_con_ciclos_con_defectos(ciclos):
    r = calcular(ciclos)["principal"]["estado_defectos"]
    assert r["pre"]["ciclos_con_indice"] == 2
    assert r["post"]["ciclos_con_indice"] == 1
    assert "ciclos_al_100" not in r


def test_sensibilidad_excluye_segun_marcas(ciclos):
    r = calcular(ciclos)
    assert r["exclusiones"] == {"A": ["CP1"], "B": ["CP1", "CP3"], "C": ["PT3"]}
    assert r["sensibilidad"]["B"]["ciclos_pre"] == 2
    assert r["sensibilidad"]["C"]["ciclos_post"] == 3
    assert r["sensibilidad"]["C"]["excluidos_con_defectos"] == 0
    assert r["sensibilidad"]["A"]["excluidos_con_defectos"] == 1


def test_severidad_y_total(ciclos):
    total = calcular(ciclos)["severidad"][-1]
    assert total["severidad"] == "Total"
    assert (total["detectados_pre"], total["corregidos_pre"]) == (3, 2)
    assert total["estado_post"] == 100.0


def test_verificar_detecta_coincidencias_y_diferencias(ciclos):
    r = calcular(ciclos)
    ok = [{"ruta": "principal.ejecuciones.pre.numerador", "valor": 19, "decimales": 0},
          {"ruta": "principal.ejecuciones.pre.indice", "valor": 59.38, "decimales": 2}]
    assert analisis_estadistico.verificar(r, ok) == []
    mal = [{"ruta": "principal.ejecuciones.pre.numerador", "valor": 20, "decimales": 0},
           {"ruta": "principal.no_existe", "valor": 1}]
    assert len(analisis_estadistico.verificar(r, mal)) == 2


def test_scripts_de_punta_a_punta(ciclos, tmp_path, capsys):
    hoja = tmp_path / "hoja_datos_1.csv"
    escribir_hoja(ciclos, hoja)
    assert construir_hoja_datos.main(["--hoja", str(hoja), "--ciclos-por-periodo", "4"]) == 0

    valores = tmp_path / "valores.json"
    valores.write_text(json.dumps({"valores": [
        {"ruta": "principal.cobertura.post.numerador", "valor": 16, "decimales": 0}]}),
        encoding="utf-8")

    assert analisis_estadistico.main(["--hoja", str(hoja)]) == 1
    assert analisis_estadistico.main(["--hoja", str(hoja), "--ciclos-por-periodo", "4",
                                      "--verificar", "--valores", str(valores)]) == 0
    assert "las 1 cifras publicadas coinciden" in capsys.readouterr().out
    md = (tmp_path / "resultados_estadisticos.md").read_text(encoding="utf-8")
    assert "Tabla 7" in md and "análisis C" in md
    assert json.loads((tmp_path / "resultados_estadisticos.json").read_text(
        encoding="utf-8"))["diseno"].startswith("muestras independientes")

    valores.write_text(json.dumps({"valores": [
        {"ruta": "principal.cobertura.post.numerador", "valor": 99, "decimales": 0}]}),
        encoding="utf-8")
    assert analisis_estadistico.main(["--hoja", str(hoja), "--ciclos-por-periodo", "4",
                                      "--verificar", "--valores", str(valores)]) == 1


def test_valores_del_articulo_bien_formados():
    datos = json.loads((RAIZ / "scripts" / "valores_articulo.json").read_text(encoding="utf-8"))
    assert len(datos["valores"]) > 150
    for v in datos["valores"]:
        assert "ruta" in v and ("valor" in v or "menor_que" in v)
