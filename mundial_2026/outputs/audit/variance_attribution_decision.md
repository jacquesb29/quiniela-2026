# Atribución causal de la compresión de varianza (F5)

Folds (F0.4): 8. Ablación de un componente por vez, walk-forward leakage-safe. F5 identifica; no corrige ni activa.

## Ranking de culpabilidad

| rank | componente | %folds_cierra_gap | recovery_tail5 | consistencia | Δlogloss | Δpenca | culpabilidad | veredicto |
|---|---|---|---|---|---|---|---|---|
| 1 | reshape | 0.625 | +0.0001 | 0.0 | +0.00000 | +0.0101 | 0.00000 | culpable_probable |
| 2 | penca_penalties | 0.0 | +0.0000 | 0.0 | +0.00000 | +0.0000 | 0.00000 | no_concluyente |
| 3 | overdispersed | 0.375 | -0.0002 | 0.0 | -0.00001 | +0.0031 | -0.00001 | no_concluyente |
| 4 | dixon_coles | 0.375 | -0.0004 | 0.0 | +0.00007 | +0.0319 | -0.00014 | no_concluyente |
| 5 | bivariate | 0.375 | -0.0004 | 0.0 | +0.00005 | +0.0004 | -0.00017 | no_concluyente |
| 6 | mu_total | 0.25 | -0.0099 | 0.0 | +0.00096 | +0.0222 | -0.00101 | no_concluyente |
| 7 | mu_clamp | 0.125 | -0.0331 | 0.2416 | +0.00317 | +0.0243 | -0.00323 | no_concluyente |

## Componente #1 (fold-a-fold)

- reshape: cierra el gap de cola en 0.625 de los folds; recovery medio tail≥5 = 8.4e-05; Δlog-loss medio = 0.0.

## Preguntas

- ¿hay culpable claro? no (no_clear_culprit)
- margen sobre el 2º: 0.0

## Decisión del gate: **no_clear_culprit**

culpable no distinguible del 2º (margen 0.0000 < 0.05)

F5 no corrige ni activa. Cualquier intervención sería una fase posterior, gated.