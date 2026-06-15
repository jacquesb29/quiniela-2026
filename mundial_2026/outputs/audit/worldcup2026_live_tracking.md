# Tracker acumulativo — Mundial 2026

**Partidos finalizados registrados: 3.** Fuente primaria: `fixtures_live_2026.json` (modo `feed`). Se auto-actualiza desde el feed con contexto real; los picks reproducen los de producción y los puntos usan la regla 8/5/3.
⚠️ Con n<30 las métricas son **exploratorias** (VALIDATION_GATE): seguimiento, no inferencia.
Sin cambios al modelo: solo medición.

## Partidos

| fecha | partido | real | pick modelo | pick Penca | pts modelo | pts Penca | result. correcto | empate | favorito ganó | mercado | T-60 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-11 | Mexico vs South Africa | 2-0 | 2-0 | 2-0 | 8.0 | 8.0 | si | no | si | si | no |
| 2026-06-12 | South Korea vs Czech Republic | 2-1 | 1-1 | 1-0 | 0.0 | 5.0 | no | no | si | si | no |
| 2026-06-12 | Canada vs Bosnia and Herzegovina | 1-1 | 2-0 | 1-0 | 0.0 | 0.0 | no | si | no | si | no |

## Métricas acumuladas

- **Accuracy 1X2 (pick modal):** 33% (1/3) — resultado implícito del marcador elegido.
- **Accuracy 1X2 (argmax probabilístico):** 67% — capacidad discriminante del modelo (ML).
- **Exact score hit rate (modal):** 33% (1/3).
- **Puntos Penca promedio:** modelo 2.67 · pick Penca 4.33 (máx 8).

### Errores por categoría
- error_marcador_exacto: 2
- error_empate: 2
- error_favorito: 1

### Empates: observados vs esperados
- Observados: **1** · Esperados (Σ prob. empate del modelo): **0.69** → desvío +0.31.

### Goles: observados vs esperados
- Total observado: **7** · esperado: **7.56** (desvío -0.56).
- Promedio por partido: observado **2.33** · esperado **2.52**.

### Rendimiento según el favorito
- **Favorito ganó** (n=2): pts modelo 4.00 · pts Penca 6.50 · exact 50%.
- **Favorito NO ganó** (n=1): pts modelo 0.00 · pts Penca 0.00 · exact 0%.

_'mercado disponible' = el feed trae odds del proveedor; 'T-60 disponible' = hay alineación confirmada. Indica disponibilidad de señal, no que se haya aplicado un ajuste._

_La fuente local solo contiene 3 finalizado(s); para más partidos hay que actualizar `fixtures_live_2026.json`. No se inventaron resultados._