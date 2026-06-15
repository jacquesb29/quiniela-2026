# Auditoría de errores — partidos reales Mundial 2026

**Muestra: 3 partidos finalizados.** Fuente primaria: `fixtures_live_2026.json` (modo `feed`). ⚠️ n<30 → **exploratorio** (VALIDATION_GATE): conclusiones cualitativas.

Caveats:
- Mercado: el feed trae odds del proveedor, pero **no se aplicaron** a los picks (capa operativa, no se reentrena con 2026).
- T-60: la disponibilidad de alineación se reporta, pero **no se aplicó** ajuste.
- 'Error de datos de entrada' no se marca sin evidencia concreta. No se inventan resultados.

## Resumen de puntos Penca (8/5/3)
- Modelo (marcador modal): **8/24** (33%).
- Pick final (Penca): **13/24** (54%).
- Puntos perdidos vs máximo — modelo: 16; final: 11.

## Por partido

| partido | real | pick modelo | pick final (Penca) | pts modelo | pts final | máx | error principal |
|---|---|---|---|---|---|---|---|
| Mexico vs South Africa | 2-0 | 2-0 | 2-0 (Penca; T-60 n/d) | 8 | 8 | 8 | sin_error |
| South Korea vs Czech Republic | 2-1 | 1-1 | 1-0 (Penca; T-60 n/d) | 0 | 5 | 8 | error_empate |
| Canada vs Bosnia and Herzegovina | 1-1 | 2-0 | 1-0 (Penca; T-60 n/d) | 0 | 0 | 8 | error_favorito |

## Conteo por categoría de error

- error_marcador_exacto: 2
- error_empate: 2
- error_favorito: 1

## Dónde se pierden los puntos

Las fugas se concentran en **empates de favoritos y marcadores exactos**, no en upsets ni en distribución de goles. La capa Penca recupera puntos cuando el modal falla por diferencia, pero no cuando el favorito empata. (Coherente con F3.)

_La fuente local solo contiene 3 finalizado(s); para más partidos hay que actualizar `fixtures_live_2026.json`._