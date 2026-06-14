# Auditoría estructural F3 (histórico)

Partidos: 1930. Observado = histórico pasado; predicho = modelo leakage-safe (solo Elo prepartido). No es validación de 2026. **F3 mide; no corrige.**

## Empates (por bucket de favorito)

| bucket | n | observado | predicho | error | veredicto |
|---|---|---|---|---|---|
| global | 1930 | 0.243523 | 0.24634 | 0.002817 | calibrado |
| parejo | 444 | 0.277027 | 0.281477 | 0.00445 | calibrado |
| favorito_leve | 604 | 0.266556 | 0.267732 | 0.001175 | calibrado |
| favorito_medio | 560 | 0.214286 | 0.235969 | 0.021683 | sobreestima_empates |
| favorito_fuerte | 322 | 0.204969 | 0.175801 | -0.029168 | subestima_empates |

## Goles totales

- media observada=2.716062, predicha=2.528577, bias=-0.187485, mae=1.445318

## Colas

| umbral | observado | predicho | abs_error |
|---|---|---|---|
| total>=4 | 0.282902 | 0.25412 | 0.028781 |
| total>=5 | 0.156477 | 0.122202 | 0.034275 |
| total>=6 | 0.074093 | 0.052432 | 0.021661 |

## Exact score

| top_n | hit_rate | cobertura |
|---|---|---|
| 1 | 0.127461 | 0.135576 |
| 3 | 0.343005 | 0.360198 |
| 5 | 0.509326 | 0.535555 |
| 10 | 0.755959 | 0.802162 |

## Penca (8/5/3)

| bucket | n | realized | expected | gap |
|---|---|---|---|---|
| global | 1930 | 2.47513 | 2.493323 | 0.018194 |
| favorito_gana | 1044 | 4.548851 | 2.567711 | -1.98114 |
| underdog_gana | 416 | 0.0 | 2.372526 | 2.372526 |
| empate | 470 | 0.059574 | 2.435006 | 2.375432 |

## Veredicto del gate

- subestima_empates: **False**
- sobreestima_favoritos: **False**
- goles_mal_calibrados: **False**
- subestima_colas: **True**
- optimismo_penca: **False**
- vale_la_pena_intervenir: **True**
- suggested_priority: **colas**

F3 no cambió ninguna predicción ni peso del modelo.