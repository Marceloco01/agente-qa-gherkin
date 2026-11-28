"""
Excepciones propias del dominio.

Fase 1: vacío a propósito. Se va a poblar a medida que aparezcan casos de error
de negocio reales (ej. en Fase 2: error al vincular Test Plan, en Fase 4: error
de alucinación bloqueante). No se inventan excepciones que todavía no se usan.
"""


class AprobacionBloqueadaError(Exception):
    """v1.0.2: se intentó aprobar un test case marcado con posible
    alucinación o sin verificación disponible."""
