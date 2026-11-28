"""v1.0.2: modelos ajustados y kappa de Cohen."""

import math

import pytest

from application.tesis.modelos_ajustados import _irls, kappa_cohen


def test_binomial_con_solo_periodo_reproduce_el_odds_ratio_agregado():
    beta, se, _ = _irls([[1, 0], [1, 1]], [201, 258], [263, 272], "binomial")
    assert math.exp(beta[1]) == pytest.approx((258 / 14) / (201 / 62), rel=1e-9)


def test_poisson_con_offset_reproduce_la_razon_de_tasas():
    beta, se, _ = _irls([[1, 0], [1, 1]], [55, 20], None, "poisson",
                        offset=[math.log(465), math.log(605)])
    assert math.exp(beta[1]) == pytest.approx((20 / 605) / (55 / 465), rel=1e-9)
    assert se[1] == pytest.approx(math.sqrt(1 / 55 + 1 / 20), rel=1e-6)


def test_kappa_acuerdo_perfecto():
    k = kappa_cohen([1, 0, 1, 1, 0], [1, 0, 1, 1, 0])
    assert k.kappa == pytest.approx(1.0)


def test_kappa_valor_conocido():

    e1 = [1] * 25 + [0] * 25
    e2 = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
    assert kappa_cohen(e1, e2).kappa == pytest.approx(0.40)


def test_kappa_rechaza_listas_distintas():
    with pytest.raises(ValueError):
        kappa_cohen([1, 0], [1])
