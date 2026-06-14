"""Candado de lenguaje de validación (F0.5).

Decide la etiqueta de validación del modelo de forma proporcional a la evidencia
y bloquea cualquier afirmación fuerte ("validado") que no esté respaldada por:
muestra suficiente, comparación fuera de muestra, superación de benchmarks
comparables y ausencia de advertencia crítica de leakage.

No toca el modelo, ni pesos, ni lambdas, ni la capa Penca. Solo etiqueta y
verifica texto.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Optional

MIN_EXPLORATORY = 30    # n < 30 -> pendiente
MIN_ROBUST = 500        # n >= 500 requerido para "validado"

LABEL_PENDIENTE = "pendiente"
LABEL_PROVISIONAL = "provisional"
LABEL_NO_SUPERADO = "medido_no_superado"
LABEL_UTILIZABLE = "utilizable_con_cautela"
LABEL_VALIDADO = "validado"

# Frases afirmativas fuertes que NO pueden aparecer si la etiqueta no es "validado".
AFFIRMATIVE_VALIDADO_PHRASES = (
    "modelo validado",
    "validado fuera de muestra",
    "está validado",
    "esta validado",
    "queda validado",
    "ha sido validado",
    "modelo ya validado",
    "completamente validado",
)


@dataclass(frozen=True)
class ValidationVerdict:
    label: str
    reason: str
    n: int
    beats_baselines: bool
    out_of_sample: bool
    leakage_warning: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def validation_label(
    *,
    n: int,
    model_logloss: Optional[float],
    baseline_logloss: Mapping[str, Optional[float]],
    out_of_sample: bool,
    leakage_warning: bool = False,
) -> ValidationVerdict:
    """Etiqueta proporcional a la evidencia.

    `baseline_logloss`: {nombre: logloss} solo de baselines con muestra comparable;
    los baselines sin muestra (p.ej. mercado con n=0) deben excluirse o pasar None.
    """

    comparable = {k: v for k, v in baseline_logloss.items() if v is not None}

    if not out_of_sample:
        return ValidationVerdict(
            label=LABEL_PROVISIONAL,
            reason="comparación no es fuera de muestra",
            n=n, beats_baselines=False, out_of_sample=out_of_sample, leakage_warning=leakage_warning,
        )
    if n < MIN_EXPLORATORY:
        return ValidationVerdict(
            label=LABEL_PENDIENTE,
            reason=f"muestra insuficiente (n={n} < {MIN_EXPLORATORY})",
            n=n, beats_baselines=False, out_of_sample=out_of_sample, leakage_warning=leakage_warning,
        )
    if not comparable or model_logloss is None:
        return ValidationVerdict(
            label=LABEL_PENDIENTE,
            reason="sin baseline comparable con muestra",
            n=n, beats_baselines=False, out_of_sample=out_of_sample, leakage_warning=leakage_warning,
        )

    best_baseline = min(comparable.values())
    beats = model_logloss < best_baseline
    if not beats:
        return ValidationVerdict(
            label=LABEL_NO_SUPERADO,
            reason=f"log-loss modelo {model_logloss:.6f} no supera al mejor baseline {best_baseline:.6f}",
            n=n, beats_baselines=False, out_of_sample=out_of_sample, leakage_warning=leakage_warning,
        )

    if leakage_warning:
        return ValidationVerdict(
            label=LABEL_UTILIZABLE,
            reason="supera baseline fuera de muestra, pero persiste advertencia de leakage sin resolver (p.ej. procedencia de features no verificada)",
            n=n, beats_baselines=True, out_of_sample=out_of_sample, leakage_warning=True,
        )
    if n < MIN_ROBUST:
        return ValidationVerdict(
            label=LABEL_UTILIZABLE,
            reason=f"supera baseline pero muestra moderada (n={n} < {MIN_ROBUST})",
            n=n, beats_baselines=True, out_of_sample=out_of_sample, leakage_warning=False,
        )

    return ValidationVerdict(
        label=LABEL_VALIDADO,
        reason=f"supera benchmarks comparables fuera de muestra con n={n} y sin advertencia de leakage",
        n=n, beats_baselines=True, out_of_sample=out_of_sample, leakage_warning=False,
    )


def assert_no_unbacked_validado(html: str, verdict: ValidationVerdict) -> None:
    """Falla si el HTML afirma 'validado' sin que el veredicto lo autorice."""

    if verdict.label == LABEL_VALIDADO:
        return
    lowered = html.lower()
    for phrase in AFFIRMATIVE_VALIDADO_PHRASES:
        if phrase in lowered:
            raise AssertionError(
                f"El dashboard afirma '{phrase}' pero la etiqueta de validación es "
                f"'{verdict.label}' (razón: {verdict.reason}). No se permite lenguaje "
                "de validación fuerte sin respaldo."
            )


__all__ = [
    "MIN_EXPLORATORY",
    "MIN_ROBUST",
    "LABEL_PENDIENTE",
    "LABEL_PROVISIONAL",
    "LABEL_NO_SUPERADO",
    "LABEL_UTILIZABLE",
    "LABEL_VALIDADO",
    "AFFIRMATIVE_VALIDADO_PHRASES",
    "ValidationVerdict",
    "validation_label",
    "assert_no_unbacked_validado",
]
