# Decisiones de mejora predictiva

Capa formal para proponer/evaluar/bloquear mejoras **sin tocar producción**. Ninguna mejora que toque pesos/lambdas/Penca queda activa sin gate walk-forward aprobado. 2026 live solo es tracking/operativo, nunca evidencia de entrenamiento.

## Evidencia leída (F0–F7 + 2026 + mercado)
- F0 validación: **validado**
- F3 prioridad: **colas** (vale_la_pena=True)
- F2.5 Elo staleness: **keep_off**
- F4.2 colas: **keep_off**
- F5 atribución: **no_clear_culprit** (bloquea F6 si no_clear_culprit)
- Mercado operativo: **True** · T-60 datos disponibles: **False**
- 2026 live: 3 finalizados, fuente primaria feed=True

## Registro por estado

### active (2)
- **results-update-feed-primary** [results_update, operativo/no-prod, gate=data_freshness, riesgo=low] — ACTIVA (operativa, no altera predicciones internas) — gate=data_freshness (aprobado): feed primario y sin inventar resultados
- **market-overlay-refine** [market, operativo/no-prod, gate=operational, riesgo=low] — ACTIVA (operativa, no altera predicciones internas) — gate=operational (aprobado): overlay de mercado operativo; no altera predicciones internas

### diagnostic_only (2)
- **t60-lineup-adjust** [t60, operativo/no-prod, gate=operational, riesgo=medium] — DIAGNÓSTICO — gate=operational (no aprobado): sin alineaciones confirmadas en el feed → no activable aún
- **elo-staleness-shrink** [elo_fifa, toca producción, gate=walk_forward_fold, riesgo=high] — DIAGNÓSTICO — gate=walk_forward_fold (no aprobado): F2.5 = keep_off (sin FIFA histórica → identidad OOS)

### proposed (2)
- **draws-favorito-uplift** [draws, toca producción, gate=walk_forward_fold, riesgo=high] — BLOQUEADA/propuesta — gate=walk_forward_fold (no aprobado): sin evidencia walk-forward fold-a-fold aprobada
- **penca-selector-tune** [penca_selector, toca producción, gate=walk_forward_fold, riesgo=high] — BLOQUEADA/propuesta — gate=walk_forward_fold (no aprobado): sin evidencia walk-forward fold-a-fold aprobada

### rejected (2)
- **tail-reweight** [tails, toca producción, gate=walk_forward_fold, riesgo=high] — RECHAZADA — gate=walk_forward_fold (no aprobado): F4.2 fold-a-fold = keep_off
- **f6-component-fix** [tails, toca producción, gate=walk_forward_fold, riesgo=high] — RECHAZADA — gate=walk_forward_fold (no aprobado): F5 = no_clear_culprit (bloquea F6 sin culpable causal)

## Reglas vigentes
- F2 (`elo-staleness-shrink`): permanece **diagnostic_only** (F2.5 keep_off).
- F4 (`tail-reweight`): permanece **rejected** (F4.2 keep_off).
- F5 `no_clear_culprit` **bloquea F6** (`f6-component-fix` rejected).
- Mercado/T-60: solo **active operativo** (overlay, no altera predicciones internas).
- Ninguna hipótesis que toque producción puede estar active sin gate walk-forward aprobado.