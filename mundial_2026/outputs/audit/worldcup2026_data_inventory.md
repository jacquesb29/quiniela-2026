# Inventario de datos 2026

- **Fuente principal usada:** `fixtures_live_2026.json` (modo `feed`).
- **Partidos totales:** 104.
- **Partidos finalizados:** 3.
- **Fecha más reciente (finalizado):** 2026-06-12.
- **¿CSV derivado desactualizado vs feed?:** no (feed=3, csv=3).

## Auditoría de valores de status

| status | count |
|---|---|
| pre | 101 |
| live | 0 |
| post | 3 |
| final | 0 |
| finished | 0 |
| ft | 3 |
| other | 0 |

_No se encontraron valores de status fuera de los esperados._
_Nota: 'ft' proviene de `status_detail`; el resto de `status_state`._

## Partidos finalizados (con marcador)

| fecha | partido | marcador |
|---|---|---|
| 2026-06-11 | Mexico vs South Africa | 2-0 |
| 2026-06-12 | South Korea vs Czech Republic | 2-1 |
| 2026-06-12 | Canada vs Bosnia and Herzegovina | 1-1 |

## Partidos excluidos y razón

Excluidos: **101** (no tienen marcador real → no finalizados).

| partido | status_state | razón |
|---|---|---|
| United States vs Paraguay | pre | sin actual_score (no jugado/sin resultado) |
| Qatar vs Switzerland | pre | sin actual_score (no jugado/sin resultado) |
| Brazil vs Morocco | pre | sin actual_score (no jugado/sin resultado) |
| Haiti vs Scotland | pre | sin actual_score (no jugado/sin resultado) |
| Australia vs Turkey | pre | sin actual_score (no jugado/sin resultado) |
| Germany vs Curacao | pre | sin actual_score (no jugado/sin resultado) |
| Netherlands vs Japan | pre | sin actual_score (no jugado/sin resultado) |
| Ivory Coast vs Ecuador | pre | sin actual_score (no jugado/sin resultado) |
| Sweden vs Tunisia | pre | sin actual_score (no jugado/sin resultado) |
| Spain vs Cape Verde | pre | sin actual_score (no jugado/sin resultado) |
| Belgium vs Egypt | pre | sin actual_score (no jugado/sin resultado) |
| Saudi Arabia vs Uruguay | pre | sin actual_score (no jugado/sin resultado) |
| Iran vs New Zealand | pre | sin actual_score (no jugado/sin resultado) |
| France vs Senegal | pre | sin actual_score (no jugado/sin resultado) |
| Iraq vs Norway | pre | sin actual_score (no jugado/sin resultado) |
| Argentina vs Algeria | pre | sin actual_score (no jugado/sin resultado) |
| Austria vs Jordan | pre | sin actual_score (no jugado/sin resultado) |
| Portugal vs Dem. Rep. of Congo | pre | sin actual_score (no jugado/sin resultado) |
| England vs Croatia | pre | sin actual_score (no jugado/sin resultado) |
| Ghana vs Panama | pre | sin actual_score (no jugado/sin resultado) |
| Uzbekistan vs Colombia | pre | sin actual_score (no jugado/sin resultado) |
| Czech Republic vs South Africa | pre | sin actual_score (no jugado/sin resultado) |
| Switzerland vs Bosnia and Herzegovina | pre | sin actual_score (no jugado/sin resultado) |
| Canada vs Qatar | pre | sin actual_score (no jugado/sin resultado) |
| Mexico vs South Korea | pre | sin actual_score (no jugado/sin resultado) |
| United States vs Australia | pre | sin actual_score (no jugado/sin resultado) |
| Scotland vs Morocco | pre | sin actual_score (no jugado/sin resultado) |
| Brazil vs Haiti | pre | sin actual_score (no jugado/sin resultado) |
| Turkey vs Paraguay | pre | sin actual_score (no jugado/sin resultado) |
| Netherlands vs Sweden | pre | sin actual_score (no jugado/sin resultado) |
| Germany vs Ivory Coast | pre | sin actual_score (no jugado/sin resultado) |
| Ecuador vs Curacao | pre | sin actual_score (no jugado/sin resultado) |
| Tunisia vs Japan | pre | sin actual_score (no jugado/sin resultado) |
| Spain vs Saudi Arabia | pre | sin actual_score (no jugado/sin resultado) |
| Belgium vs Iran | pre | sin actual_score (no jugado/sin resultado) |
| Uruguay vs Cape Verde | pre | sin actual_score (no jugado/sin resultado) |
| New Zealand vs Egypt | pre | sin actual_score (no jugado/sin resultado) |
| Argentina vs Austria | pre | sin actual_score (no jugado/sin resultado) |
| France vs Iraq | pre | sin actual_score (no jugado/sin resultado) |
| Norway vs Senegal | pre | sin actual_score (no jugado/sin resultado) |
| Jordan vs Algeria | pre | sin actual_score (no jugado/sin resultado) |
| Portugal vs Uzbekistan | pre | sin actual_score (no jugado/sin resultado) |
| England vs Ghana | pre | sin actual_score (no jugado/sin resultado) |
| Panama vs Croatia | pre | sin actual_score (no jugado/sin resultado) |
| Colombia vs Dem. Rep. of Congo | pre | sin actual_score (no jugado/sin resultado) |
| Bosnia and Herzegovina vs Qatar | pre | sin actual_score (no jugado/sin resultado) |
| Switzerland vs Canada | pre | sin actual_score (no jugado/sin resultado) |
| Morocco vs Haiti | pre | sin actual_score (no jugado/sin resultado) |
| Scotland vs Brazil | pre | sin actual_score (no jugado/sin resultado) |
| Czech Republic vs Mexico | pre | sin actual_score (no jugado/sin resultado) |
| South Africa vs South Korea | pre | sin actual_score (no jugado/sin resultado) |
| Curacao vs Ivory Coast | pre | sin actual_score (no jugado/sin resultado) |
| Ecuador vs Germany | pre | sin actual_score (no jugado/sin resultado) |
| Japan vs Sweden | pre | sin actual_score (no jugado/sin resultado) |
| Tunisia vs Netherlands | pre | sin actual_score (no jugado/sin resultado) |
| Paraguay vs Australia | pre | sin actual_score (no jugado/sin resultado) |
| Turkey vs United States | pre | sin actual_score (no jugado/sin resultado) |
| Norway vs France | pre | sin actual_score (no jugado/sin resultado) |
| Senegal vs Iraq | pre | sin actual_score (no jugado/sin resultado) |
| Cape Verde vs Saudi Arabia | pre | sin actual_score (no jugado/sin resultado) |
| Uruguay vs Spain | pre | sin actual_score (no jugado/sin resultado) |
| Egypt vs Iran | pre | sin actual_score (no jugado/sin resultado) |
| New Zealand vs Belgium | pre | sin actual_score (no jugado/sin resultado) |
| Croatia vs Ghana | pre | sin actual_score (no jugado/sin resultado) |
| Panama vs England | pre | sin actual_score (no jugado/sin resultado) |
| Colombia vs Portugal | pre | sin actual_score (no jugado/sin resultado) |
| Dem. Rep. of Congo vs Uzbekistan | pre | sin actual_score (no jugado/sin resultado) |
| Algeria vs Austria | pre | sin actual_score (no jugado/sin resultado) |
| Jordan vs Argentina | pre | sin actual_score (no jugado/sin resultado) |
| Group A 2nd Place vs Group B 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group C Winner vs Group F 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group E Winner vs Third Place Group A/B/C/D/F | pre | sin actual_score (no jugado/sin resultado) |
| Group F Winner vs Group C 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group E 2nd Place vs Group I 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group I Winner vs Third Place Group C/D/F/G/H | pre | sin actual_score (no jugado/sin resultado) |
| Group A Winner vs Third Place Group C/E/F/H/I | pre | sin actual_score (no jugado/sin resultado) |
| Group L Winner vs Third Place Group E/H/I/J/K | pre | sin actual_score (no jugado/sin resultado) |
| Group G Winner vs Third Place Group A/E/H/I/J | pre | sin actual_score (no jugado/sin resultado) |
| Group D Winner vs Third Place Group B/E/F/I/J | pre | sin actual_score (no jugado/sin resultado) |
| Group H Winner vs Group J 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group K 2nd Place vs Group L 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group B Winner vs Third Place Group E/F/G/I/J | pre | sin actual_score (no jugado/sin resultado) |
| Group D 2nd Place vs Group G 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group J Winner vs Group H 2nd Place | pre | sin actual_score (no jugado/sin resultado) |
| Group K Winner vs Third Place Group D/E/I/J/L | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 1 Winner vs Round of 32 3 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 2 Winner vs Round of 32 5 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 4 Winner vs Round of 32 6 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 7 Winner vs Round of 32 8 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 11 Winner vs Round of 32 12 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 9 Winner vs Round of 32 10 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 14 Winner vs Round of 32 16 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 32 13 Winner vs Round of 32 15 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 16 1 Winner vs Round of 16 2 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 16 5 Winner vs Round of 16 6 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 16 3 Winner vs Round of 16 4 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Round of 16 7 Winner vs Round of 16 8 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Quarterfinal 1 Winner vs Quarterfinal 2 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Quarterfinal 3 Winner vs Quarterfinal 4 Winner | pre | sin actual_score (no jugado/sin resultado) |
| Semifinal 1 Loser vs Semifinal 2 Loser | pre | sin actual_score (no jugado/sin resultado) |
| Semifinal 1 Winner vs Semifinal 2 Winner | pre | sin actual_score (no jugado/sin resultado) |

## Aviso de actualización

- **La fuente local solo contiene 3 finalizado(s).**
- **Para actualizar más partidos hay que actualizar `fixtures_live_2026.json`** (p. ej. re-ejecutando `sync_live_data_2026.py`); este módulo no inventa resultados.
- No se fabricaron marcadores: cada finalizado corresponde a un `actual_score` real del feed.