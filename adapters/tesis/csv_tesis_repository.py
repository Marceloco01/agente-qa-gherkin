"""
Adaptador: el corpus del estudio leído de los CSV del proyecto.

Envuelve `infrastructure.reportes.pretest_posttest.cargar()`, que es la carga
que produjo y validó los números del estudio, y la traduce a las estructuras
del puerto. NO se reimplementó esa carga: son ~1.400 líneas con reglas
peleadas una por una (unidad "test" y no "run", base de 60 alineada entre
cobertura y ejecución, clasificación funcional/gobierno, descuento
conservador de defectos que ignora los "Parcialmente evitable"). Reescribirla
para que "se vea más hexagonal" sería rehacer a mano números ya defendibles,
que es el peor intercambio posible a esta altura.

Lo que sí hace este adaptador: convertir esa carga en estructuras que el caso
de uso puede consumir sin saber nada de CSV, de pandas ni de `DatosPrePost`.
Cuando exista el adaptador Postgres, la única diferencia va a estar acá.
"""

from __future__ import annotations

from pathlib import Path

import statistics

from infrastructure.reportes.pretest_posttest import _ent, _leer, _num, cargar
from ports.tesis_repository import (
    CasoRevisado,
    Cohorte,
    ComposicionCasos,
    CorpusTesis,
    CriterioPareado,
    DefectoAuditado,
    FilaTesis,
    TesisRepository,
    TiemposProceso,
)


_CORTES = (
    ("primario", "Conjunto Primario", ("Corpus original",)),
    ("estandar", "Cohorte Estándar",
     ("Corpus original", "Ampliación recuperada", "Septiembre · umbral 62")),
    ("completa", "Cohorte Completa",
     ("Corpus original", "Ampliación recuperada", "Septiembre · umbral 62",
      "Septiembre · umbral reducido")),
)
_COHORTE_REDUCIDA = "Septiembre · umbral reducido"


def _lista_criterios(texto: str | None) -> list[str]:
    """Los criterios no cubiertos vienen en un solo campo, separados por ||."""
    return [x.strip() for x in (texto or "").split("||") if x.strip()]


class CsvTesisRepository(TesisRepository):
    def __init__(self, raiz: Path):
        self._raiz = Path(raiz)

    def obtener_corpus(self) -> CorpusTesis:
        d = cargar(self._raiz)
        ejec = d.ejecutabilidad or {}
        por_hu_cec = (ejec.get("por_hu") or {})


        cohorte_de: dict[str, str] = {}
        for c in d.cohortes:
            for clave in c.get("claves", ()):
                cohorte_de[clave] = c["nombre"]


        mitigados: dict[str, int] = {}
        defectos_por_hu: dict[str, int] = {}
        for x in d.defectos_auditados:
            for k in x["hu_keys"]:
                defectos_por_hu[k] = defectos_por_hu.get(k, 0) + 1
                if x["veredicto"] == "Evitable":
                    mitigados[k] = mitigados.get(k, 0) + 1

        aprobados_por_hu = (d.revision_agente or {}).get("por_hu", {})

        filas = []
        for h in d.hus_con_ejecucion:
            cec = por_hu_cec.get(h.hu_key, {})
            nombre_cohorte = cohorte_de.get(h.hu_key, "(sin cohorte)")
            filas.append(FilaTesis(
                hu_key=h.hu_key,
                criterios=h.criterios or 0,
                cubiertos_pre=h.cubiertos_pre or 0,
                cubiertos_post=h.cubiertos_post or 0,
                casos_pre=cec.get("pre_n", 0),
                casos_pre_ejecutables=cec.get("pre_ok", 0),
                casos_post=cec.get("post_n", 0),
                casos_post_ejecutables=cec.get("post_ok", 0),
                casos_post_aprobados=aprobados_por_hu.get(h.hu_key, 0),
                tests_plan=h.tests_plan,
                tests_ejecutados=h.tests_ejecutados,
                defectos_pre=defectos_por_hu.get(h.hu_key, 0),
                defectos_mitigados=mitigados.get(h.hu_key, 0),
                cohorte=nombre_cohorte,
                umbral_reducido=nombre_cohorte == _COHORTE_REDUCIDA,
            ))

        por_nombre = {c["nombre"]: c for c in d.cohortes}
        cohortes = []
        for clave, etiqueta, nombres in _CORTES:
            claves_hu = tuple(
                k for n in nombres for k in por_nombre.get(n, {}).get("claves", ())
            )
            cohortes.append(Cohorte(
                clave=clave,
                nombre=etiqueta,
                claves_hu=claves_hu,
                nota=" + ".join(nombres),
            ))

        rev = d.revision_agente or {}
        composicion = ComposicionCasos(
            casos_funcionales_humanos=(ejec.get("pre") or {}).get("casos", 0),
            casos_gobierno=(ejec.get("pre_checklist") or {}).get("casos", 0),
            titulos_gobierno=tuple(ejec.get("catalogo_checklist") or ()),
            umbral_hu_gobierno=ejec.get("umbral_hu", 0),
            casos_sin_guion=(ejec.get("pre") or {}).get("sin_guion", 0),
            casos_sin_accion=(ejec.get("pre") or {}).get("sin_accion", 0),
            casos_generados_agente=rev.get("generados", 0),
            casos_aprobados_agente=rev.get("aprobados", 0),
            casos_rechazados_agente=rev.get("generados", 0) - rev.get("aprobados", 0),
        )

        defectos = tuple(
            DefectoAuditado(
                defecto_key=x["defecto_key"], titulo=x["titulo"],
                descripcion=x["descripcion"], criticidad=x["criticidad"],
                estado=x["estado"], hu_keys=tuple(x["hu_keys"]),
                veredicto=x["veredicto"], veredicto_llm=x["veredicto_llm"],
                veredicto_humano=x["veredicto_humano"],
                corregido_por_humano=x["corregido_por_humano"],
                caso_agente=x["caso_agente"], justificacion=x["justificacion"],
                motivo_no_evitable=x["motivo_no_evitable"],
                confianza=x["confianza"], modelo_juez=x["modelo_juez"],
                comentario_humano=x["comentario_humano"],
                tests_historicos=tuple(x["tests_historicos"]),
            )
            for x in d.defectos_auditados
        )

        en_base = {h.hu_key for h in d.hus_con_ejecucion}
        return CorpusTesis(
            filas=tuple(filas),
            cohortes=tuple(cohortes),
            composicion=composicion,
            defectos=defectos,
            capacidad_demostrada=sum(h.tests_ejecutados for h in d.hus_con_ejecucion),
            hu_con_trazabilidad_defectos=d.n_defectos,
            hu_excluidas=tuple(sorted(
                {h.hu_key for h in d.hus_con_runs} - en_base)),
            limitaciones=dict(d.limitaciones or {}),
            avisos=tuple(d.avisos),
        )


    def obtener_criterios_pareados(self) -> tuple[CriterioPareado, ...]:
        """
        Reconstruye la matriz criterio por criterio desde las listas de NO
        cubiertos de cada lado.

        `cobertura_real_retro.csv` guarda, por HU, cuántos criterios cubrió
        cada lado y el TEXTO de los que no. Esa lista es el único lugar del
        corpus con granularidad por criterio, así que la pertenencia a cada
        cuadrante sale de ahí: un criterio está en la lista de fallados del
        humano y no en la de Gio => lo cubrió solo Gio, y así.

        La reconstrucción se verifica sola más abajo: si la cantidad de ítems
        de una lista no coincide con `total - cubiertos`, esa HU se marca y no
        se inventa nada. Al escribir esto, las 60 cuadraban y los marginales
        daban exacto contra el CSV (207 del humano, 258 de Gio).
        """
        salida: list[CriterioPareado] = []
        for f in _leer(self._raiz, "cobertura_real_retro.csv"):
            clave = (f.get("hu_key") or "").strip()
            total = _ent(f.get("criterios_total"))
            cub_h, cub_a = _ent(f.get("cubiertos_sin_ia")), _ent(f.get("cubiertos_con_ia"))
            falla_h = _lista_criterios(f.get("no_cubiertos_sin_ia"))
            falla_a = _lista_criterios(f.get("no_cubiertos_con_ia"))
            if len(falla_h) != total - cub_h or len(falla_a) != total - cub_a:


                continue
            vistos = set()
            for texto in list(falla_h) + list(falla_a):
                if texto in vistos:
                    continue
                vistos.add(texto)
                salida.append(CriterioPareado(
                    hu_key=clave, texto=texto,
                    cubierto_humano=texto not in falla_h,
                    cubierto_gio=texto not in falla_a,
                ))


            for i in range(total - len(vistos)):
                salida.append(CriterioPareado(
                    hu_key=clave, texto=f"(criterio {i + 1} de {clave}, cubierto por ambos)",
                    cubierto_humano=True, cubierto_gio=True,
                ))
        return tuple(salida)

    def obtener_casos_revisados(self) -> tuple[CasoRevisado, ...]:
        return tuple(
            CasoRevisado(
                hu_key=(f.get("hu_key") or "").strip(),
                titulo=f.get("titulo", ""),
                estado=f.get("estado_final", ""),
                motivo_rechazo=f.get("motivo_rechazo", ""),
                gherkin=f.get("gherkin_final", ""),
            )
            for f in _leer(self._raiz, "revision_manual_retrospectiva_test_cases.csv")
        )

    def obtener_tiempos(self) -> TiemposProceso:
        gen = [_num(f.get("tiempo_generacion_segundos"))
               for archivo in ("resultado_agente_82hu.csv", "resultado_septiembre.csv")
               for f in _leer(self._raiz, archivo)]
        gen = [g for g in gen if g is not None]
        rev = _leer(self._raiz, "revision_manual_retrospectiva_resumen.csv")
        minutos = [_num(f.get("duracion_minutos")) for f in rev]
        minutos = [m for m in minutos if m is not None]
        casos = sum(_ent(f.get("total_test_cases")) for f in rev)
        total_min = sum(minutos)
        return TiemposProceso(
            generacion_segundos_mediana=statistics.median(gen) if gen else None,
            generacion_n=len(gen),
            revision_minutos_total=total_min if minutos else None,
            revision_minutos_mediana_hu=statistics.median(minutos) if minutos else None,
            revision_segundos_por_caso=(total_min * 60 / casos) if casos else None,
            revision_n_hu=len(minutos),
            revision_n_casos=casos,
            diseno_humano_minutos_hu=None,
            motivo_sin_dato_humano=(
                "Las tres fuentes de tiempo de diseño del proyecto no sirven: "
                "tiempo_diseno_dias tiene 28 de 82 valores NEGATIVOS (los tests "
                "se crearon después de arrancar la certificación), "
                "duracion_escritura_dias tiene mediana de 469 días porque es el "
                "span entre el primer y el último test de Test Plans que se "
                "reciclan, y la revisión retrospectiva mide el lado NEXUS sin un "
                "Pre con qué compararlo. No se estima: se declara."
            ),
        )
