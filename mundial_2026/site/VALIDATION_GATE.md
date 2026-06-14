# VALIDATION_GATE.md

Estas reglas evitan que el modelo parezca más validado de lo que está.

## Reglas duras

1. No se publica una mejora predictiva si no supera baseline fuera de muestra.
2. No se cambian pesos durante el torneo salvo bug real o mejora justificada por backtest/calibración.
3. No se toma una decisión metodológica por 4 partidos.
4. No se usa ablation con `matches=0` como evidencia.
5. No se afirma mejora sin validación walk-forward o equivalente anti-leakage.
6. No se publican picks si falta fixture, lambda, distribución válida o audit trail.
7. No se usan datos posteriores al kickoff para simular predicciones prepartido.
8. No se imputan variables faltantes con narrativa subjetiva.
9. No se declara 90-95% de certeza para un marcador exacto único.
10. Si el modelo contradice fuertemente al mercado y no hay explicación trazable, se baja confianza.

## Muestra mínima

- `n < 30`: exploratorio.
- `30 <= n < 100`: preliminar.
- `100 <= n < 500`: utilizable con cautela.
- `n >= 500`: robusto, siempre que sea anti-leakage.

## Publicación del dashboard

El dashboard debe usar lenguaje proporcional a la evidencia:

- Sin histórico: “pendiente de validación”.
- Histórico parcial: “provisional”.
- Benchmark medido pero no superado: “medido, no superado”.
- Ablation con filas inválidas: “parcial/no válido”.
- Calibración 2026 con n bajo: “en medición”.

## LOCK_TOURNAMENT

`LOCK_TOURNAMENT=true` significa:

- Se actualizan resultados, lesiones, sanciones, alineaciones, descanso, fatiga, estado de grupo y mercado disponible.
- No se alteran pesos, priors o metodología por intuición.
- Todo cambio debe registrar fecha, razón, métrica antes/después, archivo afectado y si se permite durante torneo.

## NO_OVERREACTION

`NO_OVERREACTION=true` significa:

- Cada fallo se audita.
- No se parchea el marcador posterior.
- Solo se propone cambio si mejora fuera de muestra.
- Corea-Chequia, Canadá-Bosnia y USA-Paraguay son auditoría cualitativa, no autorización para overfit.
