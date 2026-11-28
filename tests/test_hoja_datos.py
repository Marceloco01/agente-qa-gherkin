"""Pruebas de application/tesis/hoja_datos.py (Hoja de datos 1)."""

import csv

from application.tesis.hoja_datos import (
    SEVERIDADES,
    Ciclo,
    desde_tabla_ancha,
    escribir_hoja,
    leer_hoja,
    leer_marcas,
    marcas_sin_ciclo,
    validar,
)


def ciclo(periodo="pre", codigo="CP1", sit=(4, 4), casos=(8, 8), defectos=None, marcas=()):
    det = defectos or {s: 0 for s in SEVERIDADES}
    return Ciclo(
        periodo=periodo, ciclo=codigo,
        situaciones_identificadas=sit[0], situaciones_cubiertas=sit[1],
        casos_especificados=casos[0], casos_ejecutados=casos[1],
        defectos_detectados=sum(det.values()), defectos_corregidos=sum(det.values()),
        detectados_por_severidad=dict(det), corregidos_por_severidad=dict(det),
        marcas=frozenset(marcas),
    )


class TestIndices:
    def test_indices_por_ciclo(self):
        c = ciclo(sit=(4, 3), casos=(10, 5))
        assert c.indice_cobertura == 75.0
        assert c.indice_ejecuciones == 50.0
        assert c.estado_defectos is None

    def test_exclusiones_por_analisis(self):
        sin_ejec = ciclo(marcas={"sin_ejecuciones"})
        no_vinc = ciclo(codigo="CP2", marcas={"ejecuciones_no_vinculadas"})
        vera = ciclo("post", "PT1", marcas={"umbral_vera_reducido"})
        assert sin_ejec.excluido_en("A") and sin_ejec.excluido_en("B")
        assert not no_vinc.excluido_en("A") and no_vinc.excluido_en("B")
        assert vera.excluido_en("C") and not vera.excluido_en("A")


class TestValidacion:
    def test_hoja_valida(self):
        assert validar([ciclo(), ciclo("post", "PT1")], esperado_por_periodo=1) == []

    def test_codigo_no_anonimo(self):
        errores = validar([ciclo(codigo="HU-123")], esperado_por_periodo=None)
        assert any("no es anónimo" in e for e in errores)

    def test_numerador_mayor_que_denominador(self):
        errores = validar([ciclo(casos=(3, 4))], esperado_por_periodo=None)
        assert any("casos" in e for e in errores)

    def test_marca_en_periodo_equivocado(self):
        errores = validar([ciclo(marcas={"umbral_vera_reducido"})], esperado_por_periodo=None)
        assert any("post-test" in e for e in errores)

    def test_marca_desconocida(self):
        errores = validar([ciclo(marcas={"otra"})], esperado_por_periodo=None)
        assert any("desconocidas" in e for e in errores)

    def test_cantidad_de_ciclos(self):
        errores = validar([ciclo()], esperado_por_periodo=60)
        assert any("se esperaban 60" in e for e in errores)

    def test_severidad_inconsistente(self):
        c = ciclo(defectos={"bajo": 1, "medio": 0, "alto": 0, "critico": 0})
        roto = Ciclo(**{**c.__dict__, "defectos_detectados": 2})
        assert any("severidad" in e for e in validar([roto], esperado_por_periodo=None))


class TestLecturaEscritura:
    def test_ida_y_vuelta(self, tmp_path):
        original = [ciclo(marcas={"sin_ejecuciones"}),
                    ciclo("post", "PT1", defectos={"bajo": 0, "medio": 1, "alto": 0, "critico": 2})]
        ruta = tmp_path / "hoja.csv"
        escribir_hoja(original, ruta)
        leidos = leer_hoja(ruta)
        assert leidos == original
        with ruta.open(encoding="utf-8-sig") as fh:
            filas = list(csv.DictReader(fh))
        assert filas[0]["excluido_A"] == "1" and filas[1]["excluido_A"] == "0"

    def test_desde_tabla_ancha_no_copia_keys_de_jira(self, tmp_path):
        ancha = tmp_path / "ancha.csv"
        campos = ["ciclo", "id_pre", "id_post"]
        for p in ("pre", "post"):
            campos += [f"situaciones_identificadas_{p}", f"situaciones_cubiertas_{p}",
                       f"casos_especificados_{p}", f"casos_ejecutados_{p}",
                       f"defectos_detectados_{p}", f"defectos_corregidos_{p}"]
            campos += [f"det_{s}_{p}" for s in SEVERIDADES] + [f"corr_{s}_{p}" for s in SEVERIDADES]
        with ancha.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=campos)
            w.writeheader()
            w.writerow({**{k: 0 for k in campos}, "ciclo": 7, "id_pre": "PROJ-123",
                        "id_post": "PT7", "situaciones_identificadas_pre": 4,
                        "situaciones_cubiertas_pre": 2, "defectos_detectados_post": 1,
                        "defectos_corregidos_post": 1, "det_critico_post": 1,
                        "corr_critico_post": 1})
        marcas = tmp_path / "marcas.csv"
        marcas.write_text("periodo,ciclo,marca\npre,CP7,sin_ejecuciones\n", encoding="utf-8")
        ciclos = desde_tabla_ancha(ancha, leer_marcas(marcas))
        pre, post = ciclos
        assert (pre.ciclo, post.ciclo) == ("CP7", "PT7")
        assert pre.indice_cobertura == 50.0
        assert pre.marcas == {"sin_ejecuciones"}
        assert post.detectados_por_severidad["critico"] == 1
        assert validar(ciclos, esperado_por_periodo=1) == []


def test_marca_que_apunta_a_un_ciclo_inexistente():
    marcas = {("post", "PT?"): frozenset({"umbral_vera_reducido"}),
              ("pre", "CP1"): frozenset({"sin_ejecuciones"})}
    errores = marcas_sin_ciclo(marcas, [ciclo()])
    assert len(errores) == 1 and "PT?" in errores[0]
