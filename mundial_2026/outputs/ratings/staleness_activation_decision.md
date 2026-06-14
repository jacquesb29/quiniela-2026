# Decisión de activación — Elo staleness-aware (F2.5)

**Decisión: keep_off** (estado operativo: diagnostic_only)

- Razón: sin diferencia relevante (sin evidencia de mejora)
- n (out-of-sample): 1520
- Δ puntos Penca prom.: 0.0
- Δ log-loss: 0.0
- Δ Brier: 0.0

## Modelos comparados (walk-forward)

| modelo | n | logloss | brier | acc | exact_acc | penca_avg |
|---|---|---|---|---|---|---|
| baseline | 1520 | 0.9950408803492171 | 0.19810797357619755 | 0.5328947368421053 | 0.14078947368421052 | 2.5092105263157896 |
| staleness_experimental | 1520 | 0.9950408803492171 | 0.19810797357619755 | 0.5328947368421053 | 0.14078947368421052 | 2.5092105263157896 |
| poisson_simple | 1520 | 1.005860193665233 | 0.20037003390756375 |  |  |  |
| elo_puro | 1520 | 1.0034737597662724 | 0.20032631077771534 |  |  |  |

## Rendimiento por bucket de staleness

| bucket | n | logloss | brier | penca_avg | nota |
|---|---|---|---|---|---|
| alto | 0 |  |  |  | sin partidos en este bucket (histórico) |
| medio | 0 |  |  |  | sin partidos en este bucket (histórico) |
| bajo | 1930 | 0.9950408803492171 | 0.19810797357619755 | 2.5092105263157896 | histórico sin FIFA: todos los partidos caen en 'bajo' |

## Limitación

El histórico `historical_matches.csv` no tiene FIFA prepartido (`fifa_rank_*_pre`/`fifa_points` vacíos) ⇒ `fifa_implied_elo=None` ⇒ el shrink staleness-aware es IDENTIDAD en walk-forward y el experimental coincide con el baseline. Por tanto no hay evidencia histórica para activar. El mecanismo solo puede usarse con FIFA/mercado ACTUALES (2026) como diagnóstico/guardrail, y esos datos NO deben usarse para activar (leakage/overfit). Decisión: mantener OFF.

## Estado del flag
`elo_staleness_enabled` permanece **False** salvo que esta decisión sea `activate`.
Esto es validación, no se ajustó el modelo ni se usaron resultados futuros/2026.