# Decisión — Intervención de colas (F4.1, experimental gated)

F4.1 es experimental y post-distribución. Flag OFF por defecto; el modelo de producción NO se modifica. No usa Mundial 2026.

Baseline: total≥4/5/6 obs 0.283/0.156/0.074 vs pred 0.254/0.122/0.052; logloss=0.99444, penca=2.4751.

| candidato | tail_err5 base→exp | Δlogloss | Δbrier | Δpenca | Δdraw_err | weak_fav | decisión |
|---|---|---|---|---|---|---|---|
| moderado | 0.0343→0.0255 | +0.00052 | +0.00009 | -0.0036 | -0.0017 | -0.0107 | **diagnostic_only** |
| fuerte | 0.0343→0.0116 | +0.00111 | +0.00020 | +0.0016 | -0.0013 | -0.0107 | **activate** |

## Resultado
Algún candidato pasa el gate → considerar activación (con doble revisión).

Flag de producción: `tail_intervention` permanece **OFF** (experimental).