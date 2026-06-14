"""Gate de activación de la intervención de colas (F4.1). Decide; no activa solo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

DECISION_ACTIVATE = "activate"
DECISION_KEEP_OFF = "keep_off"
DECISION_DIAGNOSTIC = "diagnostic_only"


@dataclass(frozen=True)
class TailGateThresholds:
    tail_improve_min: float = 0.005    # reducción mínima de |obs-pred| en total>=5
    tail_not_worse_eps: float = 0.002  # holgura para no empeorar total>=4 y >=6
    logloss_tol: float = 0.002
    brier_tol: float = 0.002
    penca_tol: float = 0.0             # Penca no puede empeorar (más allá de esto)
    weak_fav_tail_cap_pp: float = 0.01 # no inflar cola de favoritos débiles
    draw_tol: float = 0.01
    min_n: int = 500


def _f(m: Mapping, k: str) -> Optional[float]:
    v = m.get(k)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def decide_tail_activation(
    baseline: Mapping[str, object],
    experimental: Mapping[str, object],
    *,
    thresholds: TailGateThresholds = TailGateThresholds(),
) -> Dict[str, object]:
    t = thresholds
    n = int(experimental.get("n") or baseline.get("n") or 0)

    b4, e4 = _f(baseline, "tail_err_4"), _f(experimental, "tail_err_4")
    b5, e5 = _f(baseline, "tail_err_5"), _f(experimental, "tail_err_5")
    b6, e6 = _f(baseline, "tail_err_6"), _f(experimental, "tail_err_6")
    b_ll, e_ll = _f(baseline, "logloss"), _f(experimental, "logloss")
    b_br, e_br = _f(baseline, "brier"), _f(experimental, "brier")
    b_pe, e_pe = _f(baseline, "penca_avg"), _f(experimental, "penca_avg")
    b_dr, e_dr = _f(baseline, "draw_error"), _f(experimental, "draw_error")
    weak_over = _f(experimental, "weak_fav_tail_overpred") or 0.0

    improve5 = (b5 - e5) if (b5 is not None and e5 is not None) else 0.0
    not_worse_4 = (e4 is not None and b4 is not None and e4 <= b4 + t.tail_not_worse_eps)
    not_worse_6 = (e6 is not None and b6 is not None and e6 <= b6 + t.tail_not_worse_eps)
    improved_tail = improve5 > t.tail_improve_min and not_worse_4 and not_worse_6

    logloss_ok = e_ll is not None and b_ll is not None and (e_ll - b_ll) <= t.logloss_tol
    brier_ok = e_br is not None and b_br is not None and (e_br - b_br) <= t.brier_tol
    penca_ok = e_pe is not None and b_pe is not None and (e_pe - b_pe) >= -t.penca_tol
    draw_ok = e_dr is not None and b_dr is not None and (e_dr - b_dr) <= t.draw_tol
    weak_ok = weak_over <= t.weak_fav_tail_cap_pp
    n_ok = n >= t.min_n
    no_harm = logloss_ok and brier_ok and penca_ok and draw_ok and weak_ok

    if not n_ok:
        decision, reason = DECISION_KEEP_OFF, f"muestra insuficiente (n={n} < {t.min_n})"
    elif improved_tail and no_harm:
        decision, reason = DECISION_ACTIVATE, "mejora total>=5 sin empeorar >=4/>=6, log-loss, Brier, Penca ni empates"
    elif improved_tail and not no_harm:
        fails = [name for name, ok in [("log-loss", logloss_ok), ("Brier", brier_ok),
                                       ("Penca", penca_ok), ("empates", draw_ok),
                                       ("colas favoritos débiles", weak_ok)] if not ok]
        decision, reason = DECISION_DIAGNOSTIC, f"mejora colas pero rompe guard(s): {', '.join(fails)}"
    else:
        decision, reason = DECISION_KEEP_OFF, "no reduce el error en total>=5 (o empeora >=4/>=6)"

    return {
        "decision": decision, "reason": reason, "n": n,
        "improve_ge5": round(improve5, 6),
        "tail_err_4_base": b4, "tail_err_4_exp": e4,
        "tail_err_5_base": b5, "tail_err_5_exp": e5,
        "tail_err_6_base": b6, "tail_err_6_exp": e6,
        "delta_logloss": (e_ll - b_ll) if (e_ll is not None and b_ll is not None) else None,
        "delta_brier": (e_br - b_br) if (e_br is not None and b_br is not None) else None,
        "delta_penca": (e_pe - b_pe) if (e_pe is not None and b_pe is not None) else None,
        "delta_draw_error": (e_dr - b_dr) if (e_dr is not None and b_dr is not None) else None,
        "weak_fav_tail_overpred": round(weak_over, 6),
    }


__all__ = ["TailGateThresholds", "decide_tail_activation",
           "DECISION_ACTIVATE", "DECISION_KEEP_OFF", "DECISION_DIAGNOSTIC"]
