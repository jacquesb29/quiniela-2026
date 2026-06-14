# Resumen de validación final (F7)

Generado: 2026-06-14T23:01:47.805519+00:00

- Tests: **281** (OK)
- F0 (validación): etiqueta **validado**
- F1 (mercado/T-60): **operativo**
- F2.5 (Elo staleness): **keep_off**
- F3 (auditoría): prioridad sugerida **colas**, vale_la_pena=True
- F4.2 (intervención colas): **keep_off**
- F5 (atribución): **no_clear_culprit**
- F6: **not_applicable_no_clear_culprit**

## Producción
- Flags activos experimentales: ninguno (`elo_staleness_enabled`=False).
- Activo: base_model, cache_reproducibility_fix, market_t60_overlay.
- OFF: elo_staleness, tail_reweight.

F7 documenta y congela. No se cambió ninguna predicción de producción.