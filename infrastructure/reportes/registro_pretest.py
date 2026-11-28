"""
Lector del registro Pre-Test consolidado en Excel.

Este archivo lo armó el tesista a mano: es la evidencia anonimizada (HU1..HU60,
DF1..DF57) que acompaña a la tesis. El dashboard lo lee tal cual, sin recalcular
nada, para poder hacer dos cosas distintas y no confundirlas:

  1. mostrar el Pre-Test **como está declarado en el entregable**, y
  2. compararlo contra el Pre-Test que el propio sistema calcula de los CSV.

Si los dos no coinciden, la pantalla lo dice. Ese es el punto: defender dos
números distintos para el mismo indicador es la forma más fácil de perder una
sustentación, y hasta ahora nada vigilaba esa diferencia.

Las hojas se localizan por su nombre y las columnas por su encabezado, no por
número de fila. Así, si el tesista inserta una fila de título o mueve una
columna, el lector sigue funcionando en vez de leer basura en silencio.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


NOMBRE_POR_DEFECTO = "registros_pretest_60hu.xlsx"


def _norm(texto: object) -> str:
    """Minúsculas, sin tildes y sin espacios de más, para comparar encabezados."""
    s = str(texto or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _num(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace("%", "").replace(",", "."))
    except ValueError:
        return None


def _entero(v: object) -> int | None:
    n = _num(v)
    return None if n is None else int(round(n))


@dataclass
class FilaCobertura:
    hu: str
    criterios: int
    cubiertos: int

    @property
    def pct(self) -> float | None:
        return self.cubiertos / self.criterios * 100 if self.criterios else None


@dataclass
class FilaEjecucion:
    hu: str
    test_plan: str
    planificados: int
    ejecutados: int

    @property
    def pct(self) -> float | None:
        return self.ejecutados / self.planificados * 100 if self.planificados else None


@dataclass
class RegistroPreTest:
    ruta: Path
    cobertura: list[FilaCobertura] = field(default_factory=list)
    ejecucion: list[FilaEjecucion] = field(default_factory=list)
    defectos_por_criticidad: dict[str, dict[str, int]] = field(default_factory=dict)
    defectos: list[dict] = field(default_factory=list)


    declarado: dict[str, int | None] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


    @property
    def n_cobertura(self) -> int:
        return len(self.cobertura)

    @property
    def criterios_total(self) -> int:
        return sum(f.criterios for f in self.cobertura)

    @property
    def cubiertos_total(self) -> int:
        return sum(f.cubiertos for f in self.cobertura)

    @property
    def cobertura_pct(self) -> float | None:
        t = self.criterios_total
        return self.cubiertos_total / t * 100 if t else None


    @property
    def n_ejecucion(self) -> int:
        return len(self.ejecucion)

    @property
    def runs_planificados(self) -> int:
        return sum(f.planificados for f in self.ejecucion)

    @property
    def runs_ejecutados(self) -> int:
        return sum(f.ejecutados for f in self.ejecucion)

    @property
    def ejecucion_pct(self) -> float | None:
        t = self.runs_planificados
        return self.runs_ejecutados / t * 100 if t else None


    @property
    def total_defectos(self) -> int:
        return sum(v["abiertos"] + v["cerrados"]
                   for v in self.defectos_por_criticidad.values())

    @property
    def defectos_abiertos(self) -> int:
        return sum(v["abiertos"] for v in self.defectos_por_criticidad.values())

    @property
    def defectos_cerrados(self) -> int:
        return sum(v["cerrados"] for v in self.defectos_por_criticidad.values())

    def consistente(self) -> list[str]:
        """
        Chequeos internos del propio archivo. No compara contra el proyecto:
        solo verifica que el Excel no se contradiga a sí mismo.
        """
        problemas: list[str] = []
        for f in self.cobertura:
            if f.cubiertos > f.criterios:
                problemas.append(
                    f"{f.hu}: {f.cubiertos} criterios cubiertos de {f.criterios} totales")
        for f in self.ejecucion:
            if f.ejecutados > f.planificados:
                problemas.append(
                    f"{f.hu}: {f.ejecutados} runs ejecutados de {f.planificados} planificados")


        for clave, calculado, etiqueta in (
            ("cobertura_criterios", self.criterios_total, "criterios de cobertura"),
            ("cobertura_cubiertos", self.cubiertos_total, "criterios cubiertos sin IA"),
            ("ejecucion_planificados", self.runs_planificados, "runs planificados"),
            ("ejecucion_ejecutados", self.runs_ejecutados, "runs ejecutados"),
        ):
            declarado = self.declarado.get(clave)
            if declarado is not None and declarado != calculado:
                problemas.append(
                    f"{etiqueta}: la fila TOTAL declara {declarado} pero las filas "
                    f"suman {calculado}")

        if self.defectos and len(self.defectos) != self.total_defectos:
            problemas.append(
                f"el detalle lista {len(self.defectos)} defectos pero el resumen por "
                f"criticidad suma {self.total_defectos}")
        return problemas


def _hoja(wb, *claves: str):
    """Busca una hoja cuyo nombre contenga alguna de las claves."""
    for nombre in wb.sheetnames:
        n = _norm(nombre)
        if any(_norm(c) in n for c in claves):
            return wb[nombre]
    return None


def _buscar_cabecera(ws, obligatorias: tuple[str, ...], limite: int = 12):
    """
    Devuelve (fila, {clave_normalizada: indice_columna}) de la primera fila que
    contenga todos los encabezados pedidos. Buscar en vez de asumir la fila 3
    es lo que hace que insertar un título arriba no rompa nada.
    """
    for fila in range(1, min(ws.max_row, limite) + 1):
        celdas = {_norm(c.value): i for i, c in enumerate(ws[fila]) if c.value}
        if all(any(o in k for k in celdas) for o in obligatorias):
            return fila, celdas
    return None, {}


def _col(celdas: dict[str, int], *fragmentos: str) -> int | None:
    for frag in fragmentos:
        for clave, idx in celdas.items():
            if frag in clave:
                return idx
    return None


_PALABRAS_RESUMEN = ("total", "subtotal", "sin reducidas", "referencia",
                     "promedio", "media", "suma", "acumulado")


def _es_resumen(v: object) -> bool:
    n = _norm(v)
    return any(p in n for p in _PALABRAS_RESUMEN)


def _es_total(v: object) -> bool:
    return "total" in _norm(v)


def cargar_registro(raiz: Path, nombre: str = NOMBRE_POR_DEFECTO) -> RegistroPreTest | None:
    """
    Lee el Excel del registro Pre-Test. Devuelve None si no está —el dashboard
    tiene que poder arrancar sin él, igual que con los CSV que faltan—.
    """
    if load_workbook is None:
        return None
    ruta = raiz / nombre
    if not ruta.exists():
        ruta = raiz / "datos" / nombre
    if not ruta.exists():
        return None

    reg = RegistroPreTest(ruta=ruta)
    wb = load_workbook(ruta, data_only=True, read_only=True)
    try:
        _leer_cobertura(wb, reg)
        _leer_ejecucion(wb, reg)
        _leer_defectos(wb, reg)
    finally:
        wb.close()
    return reg


def _leer_cobertura(wb, reg: RegistroPreTest) -> None:
    ws = _hoja(wb, "cobertura")
    if ws is None:
        reg.avisos.append("No se encontró la hoja de cobertura.")
        return
    fila, celdas = _buscar_cabecera(ws, ("hu", "criterios", "cubiertos"))
    if fila is None:
        reg.avisos.append("La hoja de cobertura no tiene una cabecera reconocible.")
        return
    c_hu = _col(celdas, "hu")
    c_crit = _col(celdas, "criterios")
    c_cub = _col(celdas, "cubiertos")
    for f in ws.iter_rows(min_row=fila + 1, values_only=True):
        hu = f[c_hu] if c_hu is not None and c_hu < len(f) else None
        if not hu or _es_resumen(hu):


            if hu and _es_total(hu):
                reg.declarado["cobertura_criterios"] = _entero(f[c_crit])
                reg.declarado["cobertura_cubiertos"] = _entero(f[c_cub])
            break
        crit, cub = _entero(f[c_crit]), _entero(f[c_cub])
        if crit is None or cub is None:
            continue
        reg.cobertura.append(FilaCobertura(str(hu).strip(), crit, cub))


def _leer_ejecucion(wb, reg: RegistroPreTest) -> None:
    ws = _hoja(wb, "ejecucion")
    if ws is None:
        reg.avisos.append("No se encontró la hoja de ejecución.")
        return
    fila, celdas = _buscar_cabecera(ws, ("hu", "planificados", "ejecutados"))
    if fila is None:
        reg.avisos.append("La hoja de ejecución no tiene una cabecera reconocible.")
        return
    c_hu = _col(celdas, "hu")
    c_tp = _col(celdas, "test plan", "plan")
    c_plan = _col(celdas, "planificados")
    c_ejec = _col(celdas, "ejecutados")
    for f in ws.iter_rows(min_row=fila + 1, values_only=True):
        hu = f[c_hu] if c_hu is not None and c_hu < len(f) else None
        if not hu or _es_resumen(hu):
            if hu and _es_total(hu):
                reg.declarado["ejecucion_planificados"] = _entero(f[c_plan])
                reg.declarado["ejecucion_ejecutados"] = _entero(f[c_ejec])
            break
        plan, ejec = _entero(f[c_plan]), _entero(f[c_ejec])
        if plan is None or ejec is None:
            continue
        tp = f[c_tp] if c_tp is not None and c_tp < len(f) else ""
        reg.ejecucion.append(FilaEjecucion(str(hu).strip(), str(tp or "").strip(), plan, ejec))


def _leer_defectos(wb, reg: RegistroPreTest) -> None:
    ws = _hoja(wb, "defecto")
    if ws is None:
        reg.avisos.append("No se encontró la hoja de defectos.")
        return


    fila, celdas = _buscar_cabecera(ws, ("criticidad", "abiertos", "cerrados"))
    if fila is not None:
        c_cri = _col(celdas, "criticidad")
        c_ab = _col(celdas, "abiertos")
        c_ce = _col(celdas, "cerrados")
        for f in ws.iter_rows(min_row=fila + 1, values_only=True):
            nombre = f[c_cri] if c_cri is not None and c_cri < len(f) else None
            if not nombre:
                continue
            if _es_total(nombre):
                break
            ab, ce = _entero(f[c_ab]), _entero(f[c_ce])
            if ab is None and ce is None:
                continue
            reg.defectos_por_criticidad[str(nombre).strip()] = {
                "abiertos": ab or 0, "cerrados": ce or 0}
    else:
        reg.avisos.append("La hoja de defectos no tiene el resumen por criticidad.")


    inicio = (fila or 1) + len(reg.defectos_por_criticidad) + 1
    for f2 in range(inicio, min(ws.max_row, inicio + 30) + 1):
        celdas2 = {_norm(c.value): i for i, c in enumerate(ws[f2]) if c.value}
        if any("defecto" in k for k in celdas2) and any("criticidad" in k for k in celdas2):
            c_id = _col(celdas2, "defecto")
            c_cri = _col(celdas2, "criticidad")
            c_est = _col(celdas2, "estado")
            for f in ws.iter_rows(min_row=f2 + 1, values_only=True):
                ident = f[c_id] if c_id is not None and c_id < len(f) else None
                if not ident or _es_total(ident):
                    continue
                reg.defectos.append({
                    "id": str(ident).strip(),
                    "criticidad": str(f[c_cri] or "").strip() if c_cri is not None else "",
                    "estado": str(f[c_est] or "").strip() if c_est is not None else "",
                })
            break


def conciliar(reg: RegistroPreTest, datos) -> list[dict]:
    """
    Compara el Pre-Test declarado en el Excel contra el que el sistema calcula
    de los CSV. `datos` es el DatosPrePost de infrastructure.reportes.pretest_posttest.

    Devuelve una fila por indicador con ambos valores y si coinciden. Una
    diferencia NO es necesariamente un error --el Excel tiene 60 HU y los CSV
    47/43--, pero tiene que estar a la vista y explicada, no escondida.
    """
    def cmp(etiqueta, excel, calc, unidad, tol, nota):
        coincide = (excel is not None and calc is not None
                    and abs(excel - calc) <= tol)
        return {"indicador": etiqueta, "excel": excel, "calculado": calc,
                "unidad": unidad, "coincide": coincide, "nota": nota}

    return [
        cmp("Cobertura de criterios (Pre)", reg.cobertura_pct,
            datos.cobertura_pre_pct, "%", 0.05,
            f"Excel: {reg.n_cobertura} HU · {reg.criterios_total} criterios. "
            f"Sistema: {datos.n_cobertura} HU · {datos.criterios_evaluados} criterios."),


        cmp("Índice de ejecución", reg.ejecucion_pct,
            datos.ejecucion_corpus_pct, "%", 0.05,
            f"Excel: {reg.n_ejecucion} HU · {reg.runs_planificados} runs "
            f"(corpus cerrado del análisis retrospectivo). "
            f"Sistema, mismo alcance: {datos.n_ejecucion_corpus} HU. "
            f"El indicador del tablero se calcula hoy sobre "
            f"{datos.n_ejecucion} HU ("
            + (f"{datos.ejecucion_pre_pct:.1f}%"
               if datos.ejecucion_pre_pct is not None else "s/d")
            + "), porque se incorporaron los runs de las recuperadas y de "
              "septiembre."),
        cmp("Defectos reales", float(reg.total_defectos),
            float(datos.total_defectos_pre), "defectos", 0.5,
            f"Excel: {len(reg.defectos)} filas de detalle. "
            f"Sistema: desglose por criticidad de defectos_severidad_resumen_retro.csv."),
    ]


@dataclass
class HUNueva:
    """
    Una HU que ya pasó el triaje (tiene criterios contados y Test Plan) pero
    a la que el agente todavía no corrió. Aporta al corpus *identificado*, no
    al *medido*: la distinción es la que impide inflar el indicador.
    """
    key: str
    criterios: int
    test_plan: str = ""
    depende_de_imagen: bool = False


def cargar_triaje(raiz: Path, nombre: str = "triaje_hu_nuevas.csv") -> list[HUNueva]:
    """
    Lee el CSV que deja scripts/triar_hu_nuevas.py y devuelve solo las que
    quedaron en el cajón LISTA. Si el archivo no está, devuelve lista vacía:
    el dashboard tiene que funcionar igual antes de correr el triaje.
    """
    import csv

    ruta = raiz / nombre
    if not ruta.exists():
        ruta = raiz / "datos" / nombre
    if not ruta.exists():
        return []

    out: list[HUNueva] = []
    with ruta.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if (fila.get("cajon") or "").strip().upper() != "LISTA":
                continue
            try:
                crit = int(fila.get("criterios") or 0)
            except ValueError:
                continue
            out.append(HUNueva(
                key=(fila.get("hu_key") or "").strip(),
                criterios=crit,
                test_plan=(fila.get("test_plan_key") or "").strip(),
                depende_de_imagen=(fila.get("depende_de_imagen") or "").strip().upper() == "SI",
            ))
    return sorted(out, key=lambda h: h.key)


UMBRAL_PRODUCCION = 62


def cargar_scores_vera(raiz: Path,
                       nombre: str = "resultado_septiembre.csv") -> dict[str, int]:
    """
    Devuelve {hu_key: vera_score} de las HU que Vera APROBÓ. Las bloqueadas
    quedan fuera: no aportan al corpus, así que su score no dice nada sobre
    con qué criterio entró una HU que sí está.
    """
    import csv

    ruta = raiz / nombre
    if not ruta.exists():
        ruta = raiz / "datos" / nombre
    if not ruta.exists():
        return {}

    out: dict[str, int] = {}
    with ruta.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            aprobada = (fila.get("vera_aprobada") or "").strip().lower()
            if aprobada not in ("true", "1", "si", "sí"):
                continue
            key = (fila.get("hu_key") or "").strip()
            try:
                score = int(float(fila.get("vera_score") or ""))
            except ValueError:
                continue
            if key:
                out[key] = score
    return out
