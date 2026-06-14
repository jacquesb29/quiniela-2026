# CHANGELOG_FINAL — Quiniela Mundial 2026

Resumen del trabajo de validación, mercado, diagnóstico e intervenciones (gated).
**F7 documenta y congela; no cambia el modelo.**

## Validación (F0)
- Backtest conectado al modelo de producción real (deja de ser proxy Elo-only).
- Ablation honesta, comparación pareada vs Poisson/Elo/mercado, candado de "validado".
- Corregido el **bug de caché mutable** (reproducibilidad; `predict_match` determinista) — único cambio aplicado a producción, sin tocar pesos/lambdas/Penca.
- Walk-forward (F0.4): el modelo **supera a Poisson y Elo** fuera de muestra (8 folds, 1520 test).
- F0.4b: Elo histórico **sin leakage** (pearson ≈1.0) → etiqueta **`validado`**.

## Mercado y T-60 (F1)
- Ingesta manual de odds + de-vig, gap modelo-mercado, regla de decisión, flujo T-60, dashboard y pipeline único.
- Capa **operativa de recomendación**; no altera predicciones internas.

## Elo staleness (F2)
- Detección (FIFA vs Elo + actividad reciente), reportes y mecanismo de shrink gated.
- **Gate F2.5: `keep_off`** (sin FIFA histórica → sin evidencia). Diagnóstico; flag OFF.

## Auditoría estructural (F3)
- Empates calibrados, exact score honesto, Penca global calibrado.
- **Colas subestimadas** (≥4 −10%, ≥5 −22%, ≥6 −29%; sesgo de goles −0.187).

## Intervención de colas (F4) — RECHAZADA
- F4.1: candidato mejoró colas en agregado (gate agregado `activate`).
- **F4.2 (fold-a-fold): `keep_off`** — solo 25% de folds mejoran; artefacto de agregación. Flag OFF.

## Atribución de varianza (F5) — `no_clear_culprit`
- Re-composición bit-idéntica validada; ablación de 7 componentes fold-a-fold.
- **`no_clear_culprit`**: la compresión de colas no se localiza en un componente; subir μ/varianza empeora la calibración fuera de muestra.

## F6 — NO PROCEDE
- Sin culpable causal claro, no hay componente que corregir. No se implementa.

## Estado final
- Modelo **validado y congelado** (`MODEL_LOCK.md`).
- Producción: modelo base + fix de reproducibilidad + capa Mercado/T-60 (recomendación).
- OFF: Elo staleness, intervención de colas.
- Operación de la quiniela: ver `QUINIELA_OPERATION_GUIDE.md`.
