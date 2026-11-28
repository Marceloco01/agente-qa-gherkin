"""
Streamlit falso: ejecuta una página de verdad y captura lo que mostró.

No es un mock de conveniencia. Es la única forma que tiene este proyecto de
verificar una pantalla sin navegador, y ya atrapó bugs reales (texto que
caducó, agregados calculados sobre el conjunto equivocado, SVG con `None`).

Distingue VISIBLE de PLEGADO: lo que está dentro de un `expander` existe pero
no cuenta para el presupuesto de texto en pantalla.
"""

from __future__ import annotations

import contextlib


class _Registro:
    def __init__(self) -> None:
        self.markdown: list[str] = []
        self.texto_visible: list[str] = []
        self.texto_plegado: list[str] = []
        self.dataframes: list[object] = []
        self.descargas: list[dict] = []
        self.config: dict = {}
        self.errores: list[str] = []
        self.plegado = 0

    def _add(self, cuerpo: str) -> None:
        (self.texto_plegado if self.plegado else self.texto_visible).append(str(cuerpo))


REG = _Registro()


class _Col:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, nombre):
        return getattr(_MODULO, nombre)


class _Expander:
    def __enter__(self):
        REG.plegado += 1
        return self

    def __exit__(self, *a):
        REG.plegado -= 1
        return False

    def __getattr__(self, nombre):
        return getattr(_MODULO, nombre)


class _FakeStreamlit:

    def markdown(self, cuerpo="", **kw):
        REG.markdown.append(str(cuerpo))
        REG._add(cuerpo)

    def write(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def caption(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def text(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def title(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def header(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def subheader(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def error(self, cuerpo="", **kw):
        REG.errores.append(str(cuerpo))
        REG._add(cuerpo)

    def warning(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def info(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def success(self, cuerpo="", **kw):
        REG._add(cuerpo)

    def metric(self, label="", value="", delta=None, **kw):
        REG._add(f"{label} {value} {delta or ''}")

    def dataframe(self, datos=None, **kw):
        REG.dataframes.append(datos)

    def table(self, datos=None, **kw):
        REG.dataframes.append(datos)

    def download_button(self, label="", data=None, file_name="", **kw):
        REG.descargas.append({"label": label, "file_name": file_name, "data": data})
        return False

    def button(self, *a, **kw):
        return False


    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Col() for _ in range(n)]

    def expander(self, *a, **kw):
        return _Expander()

    def container(self, *a, **kw):
        return _Col()

    def tabs(self, nombres, **kw):
        return [_Col() for _ in nombres]

    def set_page_config(self, **kw):
        REG.config = kw

    def divider(self, *a, **kw):
        pass


    def selectbox(self, label, opciones, index=0, **kw):
        return list(opciones)[index] if opciones else None

    def radio(self, label, opciones, index=0, **kw):
        return list(opciones)[index] if opciones else None

    def checkbox(self, label, value=False, **kw):
        return value

    def slider(self, label, min_value=None, max_value=None, value=None, **kw):
        return value if value is not None else min_value

    def number_input(self, label, min_value=None, value=None, **kw):
        return value if value is not None else min_value

    def text_input(self, label, value="", **kw):
        return value

    def date_input(self, label, value=None, **kw):
        return value

    def spinner(self, *a, **kw):
        return contextlib.nullcontext()

    def cache_data(self, *a, **kw):
        def deco(fn):
            return fn
        return deco(a[0]) if a and callable(a[0]) else deco

    def __getattr__(self, nombre):
        def _noop(*a, **kw):
            return None
        return _noop


_MODULO = _FakeStreamlit()


def instalar():
    """Pone el falso en sys.modules y devuelve el registro, ya limpio."""
    import sys

    global REG
    REG = _Registro()
    sys.modules["streamlit"] = _MODULO
    return REG
