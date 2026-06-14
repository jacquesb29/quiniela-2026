# MODEL_LOCK — Congelamiento del modelo

## Versión
- **Versión final:** quiniela-2026 F7-lock
- **Fecha de cierre:** 2026-06-14
- **Baseline congelado de referencia:** `modelo_quiniela_2026_v1_base.py` (commit/SHA registrados allí)

## Estado de validación
- Modelo **validado fuera de muestra** vs Poisson simple y Elo puro en walk-forward (F0.4; 8 folds, 1520 partidos de test).
- Elo histórico **verificado sin leakage** (F0.4b; re-derivación independiente pearson ≈1.0).
- Etiqueta vigente en `outputs/validation_status.json`: **`validado`** (alcance: histórico vs Poisson/Elo; **no** vs mercado).

## Tests
- Suite completa verde al cierre (ver `outputs/final/final_validation_summary.json` para el total exacto de la corrida final).

## Flags
- **Activos (producción):** ninguno experimental. Solo el modelo base + fix de reproducibilidad (caché) + capa operativa Mercado/T-60 (recomendación, no altera predicciones).
- **OFF:**
  - `elo_staleness_enabled = False` (worldcup2026/config.py) — F2.
  - Intervención de colas `tail_reweight` (F4) — experimental, sin flag de producción, no cableada.

## Por qué F2 NO se activa
- F2.5 (gate de activación) dio **`keep_off`**: el histórico no tiene FIFA prepartido → el shrink staleness-aware es identidad en walk-forward → **sin evidencia** out-of-sample. Queda como diagnóstico.

## Por qué F4/F5 NO se activan
- **F4.2** (walk-forward fold-a-fold): **`keep_off`**. La mejora de colas de F4.1 era artefacto de agregación; solo 25% de folds mejoraban.
- **F5** (atribución causal): **`no_clear_culprit`**. Ningún componente cierra el gap de cola de forma consistente y distinguible; subir μ/varianza empeora la calibración fold-a-fold.
- **F6 (corrección del componente): NO PROCEDE** — sin culpable causal claro no hay objetivo que intervenir.

## Regla de congelamiento
**No se toca producción (pesos, lambdas, metodología, selector Penca, flags) sin un NUEVO gate** que demuestre mejora out-of-sample fold-a-fold sin daño en log-loss/Brier/Penca/empates, con muestra suficiente y sin leakage. Cualquier reactivación de F2/F4 o un eventual F6 exige nueva evidencia walk-forward y registro en `MODEL_AUDIT.md` + `validation_status.json`. El candado `assert_no_unbacked_validado` permanece vigente.
