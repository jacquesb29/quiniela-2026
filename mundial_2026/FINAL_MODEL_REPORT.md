# FINAL_MODEL_REPORT — Quiniela Mundial 2026

Cierre del proyecto. Resume qué quedó **validado**, qué quedó **solo diagnóstico**
y qué quedó **bloqueado por gates**. **No se cambió el modelo en F7.**

## Estado por fase

### F0 — Reparación de validación (TERMINADO, productivo)
- El backtest dejó de ser un proxy Elo-only: ahora ejecuta el modelo de producción real (`backtest_production_adapter`).
- Ablation honesta (distingue features ausentes), comparación pareada vs Poisson/Elo/mercado, candado de lenguaje "validado".
- **Bug de caché mutable corregido** (única corrección aplicada a producción; solo reproducibilidad, sin tocar pesos/lambdas/Penca) → `predict_match` determinista.
- **Walk-forward (F0.4):** 8 folds expanding (min_train=400, step=200), 1520 partidos de test. El modelo **supera** a Poisson simple (log-loss ≈0.9950 vs 1.0059) y a Elo puro (1.0035) fuera de muestra.
- **F0.4b:** el Elo histórico `elo_*_pre` se verificó **sin leakage** (re-derivación walk-forward independiente reproduce el almacenado con pearson ≈1.0, diferencia máxima 0.0005). `leakage_warning=False`.
- **Etiqueta de validación: `validado`** (alcance: fuera de muestra vs Poisson/Elo en histórico Mundial/Euro/Copa América; **no** validado contra mercado —sin odds históricas—; track 2026 exploratorio).

### F1 — Mercado y T-60 (TERMINADO, operativo)
- Ingesta manual de odds + de-vig sin vig (1X2/OU/handicap), gap modelo-mercado, regla de decisión, flujo T-60, dashboard y pipeline único (`run_market_t60_pipeline.py`).
- Es una **capa operativa de recomendación**: lee outputs y produce picks/avisos; **no modifica las predicciones internas del modelo**.

### F2 — Elo staleness-aware (TERMINADO → OFF, diagnóstico)
- Detección de staleness (FIFA vs Elo + actividad reciente), reporte por equipo y por partido, mecanismo de shrink gated.
- **Gate F2.5: `keep_off`** — sin FIFA histórica, el shrink es identidad en walk-forward → sin evidencia para activar. **Solo diagnóstico.** `elo_staleness_enabled=False`.

### F3 — Auditoría estructural (TERMINADO, diagnóstico)
- Empates **globalmente calibrados**; exact score **honestamente calibrado**; Penca global calibrado.
- **Colas subestimadas:** total≥4 −10%, ≥5 −22%, ≥6 −29%; sesgo de goles totales −0.187. Gate: `suggested_priority=colas`.

### F4 — Intervención de colas (TERMINADO → OFF, rechazada)
- **F4.1:** candidato "fuerte" mejoró colas en agregado (tail≥5 0.034→0.012) → gate agregado `activate`.
- **F4.2 (fold-a-fold):** **`keep_off`** — solo 25% de folds mejoran; la mejora era artefacto de agregación. **No se activa.** Flag OFF.

### F5 — Atribución causal (TERMINADO → `no_clear_culprit`)
- Re-composición bit-idéntica de la distribución de producción (validada). Ablación de 7 componentes fold-a-fold.
- **Resultado: `no_clear_culprit`.** Ningún componente cierra el gap de cola de forma consistente y distinguible; subir μ/varianza **empeora** la calibración fold-a-fold. La compresión no se localiza causalmente.

### F6 — NO PROCEDE
- F6 (corregir el componente culpable) **no aplica**: F5 devolvió `no_clear_culprit`. No hay objetivo causal que intervenir; intervenir a ciegas degrada la calibración fuera de muestra (ya demostrado en F4.2). **No se implementa.**

## Qué está activo en producción
- El **modelo base** (validado históricamente vs Poisson/Elo, Elo sin leakage).
- El **fix de caché mutable** (reproducibilidad).
- La **capa operativa Mercado/T-60** (recomendaciones de pick; no altera predicciones internas).

## Qué está OFF
- `elo_staleness_enabled = False` (F2).
- Intervención de colas `tail_reweight` (F4): experimental, sin flag de producción, **no cableada**.

## Qué es solo diagnóstico
- Reportes de staleness (F2.1/F2.2/F2.4), auditoría estructural (F3), evaluación de intervención (F4.1/F4.2) y atribución de varianza (F5).

## Gates que bloquearon cambios
- **F0.5** (candado "validado"): solo permite "validado" con evidencia out-of-sample suficiente.
- **F2.5**: bloqueó la activación del Elo staleness (sin evidencia histórica).
- **F4.2**: bloqueó la intervención de colas (no generaliza fold-a-fold).
- **F5**: `no_clear_culprit` → bloquea F6.

## Conclusión
El modelo queda **validado fuera de muestra** y **congelado**. Las mejoras candidatas (Elo staleness, colas) fueron correctamente **bloqueadas por falta de evidencia generalizable**. La operación de la quiniela se apoya en el modelo base + la capa Mercado/T-60. No se toca producción sin un nuevo gate (ver `MODEL_LOCK.md`).
