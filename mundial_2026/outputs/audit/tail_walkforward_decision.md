# Validación walk-forward F4.2 — candidato 'fuerte' (fold-a-fold)

Reusa exactamente los folds de F0.4 (expanding, min_train=400, step=200). Es validación: NO activa nada; el flag de producción sigue OFF.

- Folds: 8
- Folds que MEJORAN tail≥5: **2**; que empeoran: **6** (fracción de mejora = 0.25)
- ¿Mejora concentrada en pocos folds? posible
- Estabilidad (media Δlog-loss / Δtail5):
  - Δlog-loss media=0.001058 (std 0.002194)
  - Δtail5 media=0.012836 (std 0.01464)
  - Δpenca media=0.004805
  - Δempates media=0.001753

## Por fold

| fold | n_test | tail5 base→exp | Δlogloss | Δpenca |
|---|---|---|---|---|
| 1 | 200 | 0.038611→0.020886 | +0.00438 | +0.0000 |
| 2 | 197 | 0.010034→0.009083 | +0.00419 | -0.0254 |
| 3 | 199 | 0.000698→0.021296 | -0.00107 | +0.0000 |
| 4 | 199 | 0.000244→0.017605 | -0.00138 | +0.0000 |
| 5 | 199 | 0.015623→0.038705 | -0.00083 | +0.0151 |
| 6 | 200 | 0.00795→0.015293 | +0.00253 | +0.0000 |
| 7 | 199 | 0.00693→0.032507 | -0.00012 | +0.0251 |
| 8 | 127 | 0.012768→0.040171 | +0.00077 | +0.0236 |

## Preguntas

- ¿cuántos folds mejoran? 2/8
- ¿cuántos empeoran? 6/8
- ¿hay evidencia de sobreajuste? revisar (mejora no mayoritaria)
- ¿la mejora es consistente? no concluyente

## Decisión walk-forward: **keep_off**

solo 25% de folds mejoran tail>=5 (<60%); tail>=4 empeora en demasiados folds; tail>=6 empeora en demasiados folds

Flag de producción: permanece **OFF** (F4.2 es validación; no activa).