# Modelo probabilistico para quiniela del Mundial 2026

Este modulo deja una base reproducible para predecir marcadores y probabilidades de clasificacion de cara al Mundial 2026.
La nueva version ya incorpora variables macro, historicas, tacticas, disciplinares y de plantilla, usando proxies cuando el dato exacto no esta disponible.

## Que modela

- Fuerza base por seleccion usando Elo internacional.
- Puntos FIFA y ranking FIFA oficiales como senal estructural secundaria.
- PIB/recursos del pais como proxy de capacidad de preparacion.
- Historial de Copas del Mundo y trayectoria futbolistica.
- Experiencia proxy del entrenador.
- Calidad de plantilla y profundidad de banco.
- Estadisticas proxy de jugadores por posicion: ataque, creacion, defensa, porteria, caps, disponibilidad, disciplina y juego aereo.
- Disciplina: amarillas, rojas y riesgo de suspension.
- Moral antes del partido y actualizacion de estado despues de partidos reales.
- Actualizacion dinamica de Elo, forma reciente, forma ofensiva, forma defensiva, fatiga, disponibilidad y disciplina despues de cada resultado cargado.
- Presion de grupo: puntos previos, diferencia de gol y partidos jugados.
- Ajuste estructural por confederacion.
- Pelota parada, pressing, ritmo de juego y flexibilidad tactica.
- Ventaja de local o sede.
- Dias de descanso.
- Lesiones o ausencias relevantes.
- Viaje acumulado y resiliencia al viaje.
- Altitud y estres climaticos.
- Partido de grupo o de eliminacion directa.
- Distribucion exacta de marcadores con ensamble de goles: Poisson simple, Dixon-Coles, sobredispersion, bivariante y optimizacion Penca. Poisson queda como benchmark, no como unica fuente del marcador.

## Cobertura inicial de datos

- Fecha de corte: 16 de marzo de 2026.
- 42 clasificados confirmados.
- 16 selecciones en repechaje UEFA por 4 cupos.
- 6 selecciones en repechaje FIFA por 2 cupos.

## Archivos

- `teams_2026.json`: dataset base de selecciones, Elo y ranking FIFA oficial.
- `modelo_quiniela_2026.py`: CLI para prediccion, perfiles internos y simulacion Monte Carlo del torneo.
- `modelo_quiniela_2026_v1_base.py`: checkpoint congelado del modelo v1 en commit `0370dfd` con SHA-256. Sirve como base fija para comparar mejoras futuras.
- `data/historical_match_master_schema.json`: esquema de tabla maestra historica para backtesting temporal sin fuga de informacion futura.
- `data/prediction_operating_system_2026.json`: protocolo operativo para usar el modelo durante el Mundial sin sobreajustarlo: congelacion final, re-simulacion diaria, alertas, estrategia Penca y auditoria post-jornada.
- `sync_fifa_rankings.py`: refresca `fifa_points` y `fifa_rank` desde el endpoint oficial de FIFA.
- `fixtures_template.json`: ejemplo de formato para cargar partidos con estado dinamico.
- `tournament_2026_draw.json`: draw oficial del Mundial 2026 con placeholders de repechaje.
- `runtime/tournament_state_2026.json`: estado persistente que el modelo actualiza automaticamente entre ejecuciones.

Solo se ejecuta `modelo_quiniela_2026.py`. Los archivos `.json` no se ejecutan: se usan como entradas o como estado guardado.

## Validacion y no fuga de informacion

La mejora predictiva no se mide subiendo porcentajes a mano. A partir de esta version, el proyecto deja tres candados metodologicos:

- Baseline v1 congelado: `modelo_quiniela_2026_v1_base.py` fija commit, hash y componentes del modelo base. Si una mejora nueva no supera ese baseline en Brier, log-loss, calibracion y puntos esperados Penca, no debe considerarse mejora real.
- Tabla maestra historica: `data/historical_match_master_schema.json` define los campos permitidos para Mundial, Euro, Copa America, Nations League y eliminatorias. Cada variable indica si es pre-torneo, pre-partido, live o target, para evitar usar informacion conocida despues del partido.
- Tres modos separados: pre-torneo usa senales estructurales; pre-partido agrega lesiones, descanso, mercado y alineacion probable; live agrega minuto, marcador, eventos, tarjetas y momentum. Una variable live no puede contaminar un backtest pre-partido.

La optimizacion Penca tambien queda separada de la prediccion futbolistica: el marcador mas probable del modelo puede no ser el marcador que maximiza puntos esperados bajo regla Penca. Por eso la web debe mostrar ambos cuando difieran.

## Sistema operativo durante el Mundial

El proyecto no debe seguir cambiando metodologia infinitamente. La regla operativa queda documentada en `data/prediction_operating_system_2026.json`:

- Antes del torneo: congelar `modelo_quiniela_2026_final_pre_torneo.py` solo despues de backtesting, calibracion, ablations y benchmarks.
- Durante el torneo: actualizar datos, noticias, lesiones, alineaciones, mercado, estado dinamico y feed live; no cambiar pesos ni funciones principales salvo bug real.
- Despues de cada jornada: re-simular, comparar contra el snapshot anterior, emitir alertas, revisar fallos y ajustar estrategia Penca segun posicion, no la metodologia.
- Despues del torneo: auditar Brier, log-loss, 1X2, clasificados, finalistas, campeon top 3/top 5 y puntos Penca contra benchmarks.

## Uso rapido

Primero entra a la carpeta del proyecto:

```bash
cd "/Users/jacquesbentata/Documents/New project"
```

Listar selecciones:

```bash
python3 mundial_2026/modelo_quiniela_2026.py list-teams
```

Predecir un partido:

```bash
python3 mundial_2026/modelo_quiniela_2026.py predict Spain Mexico --neutral --knockout --show-factors
```

Tambien puedes usar nombres en espanol o con acentos:

```bash
python3 mundial_2026/modelo_quiniela_2026.py predict "España" Uruguay
```

Predecir un partido con Monte Carlo:

```bash
python3 mundial_2026/modelo_quiniela_2026.py predict "España" Uruguay --monte-carlo 15000 --seed 7
```

Predecir un partido de eliminacion directa con prorroga y penales:

```bash
python3 mundial_2026/modelo_quiniela_2026.py predict "España" Uruguay --stage round16 --monte-carlo 15000 --seed 7
```

Predecir con contexto de sede, disciplina y grupo:

```bash
python3 mundial_2026/modelo_quiniela_2026.py predict Mexico Morocco \
  --home-team Mexico \
  --venue-country Mexico \
  --group A \
  --group-points-a 3 \
  --group-points-b 1 \
  --group-matches-played-a 1 \
  --group-matches-played-b 1 \
  --morale-a 0.08 \
  --morale-b -0.02 \
  --yellow-cards-a 1 \
  --yellow-cards-b 2 \
  --rest-a 5 \
  --rest-b 4 \
  --altitude 1500 \
  --travel-a 250 \
  --travel-b 8700
```

Ver tabla de fuerza y gol esperado frente a un rival promedio del Mundial:

```bash
python3 mundial_2026/modelo_quiniela_2026.py power-table
```

Ver probabilidades de clasificacion desde los repechajes:

```bash
python3 mundial_2026/modelo_quiniela_2026.py playoffs --iterations 15000
```

Simular el torneo completo con Monte Carlo:

```bash
python3 mundial_2026/modelo_quiniela_2026.py simulate-tournament --iterations 15000 --top 20
```

Simular el torneo completo usando el draw oficial incluido:

```bash
python3 mundial_2026/modelo_quiniela_2026.py simulate-tournament \
  --config mundial_2026/tournament_2026_draw.json \
  --iterations 15000 \
  --top 24
```

Procesar una quiniela propia desde JSON:

```bash
python3 mundial_2026/modelo_quiniela_2026.py fixtures mundial_2026/fixtures_template.json
```

El archivo JSON puede incluir `stage` con uno de estos valores:
`group`, `round32`, `round16`, `quarterfinal`, `semifinal`, `third_place`, `final`

Tambien acepta aliases mas cortos:
`round8` = `quarterfinal`
`round4` = `semifinal`
`third_and_fourth_place` = `third_place`

Si un partido real de knockout se va a proroga o penales, agrega ademas:
- `went_extra_time: true`
- `went_penalties: true` si hubo tanda
- `penalties_winner: "A"`, `"B"` o el nombre del equipo ganador

En esos casos `actual_score_a` y `actual_score_b` deben ser el marcador despues de los 120 minutos, no la tanda de penales.

Ver el estado persistente actual:

```bash
python3 mundial_2026/modelo_quiniela_2026.py state-show
```

Ver el estado persistente de una seleccion:

```bash
python3 mundial_2026/modelo_quiniela_2026.py state-show --team Argentina
```

Reiniciar el estado persistente:

```bash
python3 mundial_2026/modelo_quiniela_2026.py state-reset
```

Inspeccionar todas las variables internas de una seleccion:

```bash
python3 mundial_2026/modelo_quiniela_2026.py team-profile Argentina
```

Refrescar puntos y ranking FIFA oficiales en `teams_2026.json`:

```bash
python3 mundial_2026/sync_fifa_rankings.py
```

## Notas

- Esta version no intenta decir que ya existen los 48 participantes finales: al 16 de marzo de 2026 todavia faltan por definirse 6 cupos.
- Si quieres afinar el modelo, la mejora mas fuerte es reemplazar los proxies por datos reales de convocatorias finales, xG, cargas fisicas, entrenadores confirmados, tarjetas acumuladas y estadisticas por jugador.
- Las variables de jugadores estan modeladas con una plantilla proxy reproducible cuando no hay lista real; si agregas `players` por equipo en `teams_2026.json`, el modelo puede usar esos valores en lugar de las estimaciones.
- Para una quiniela completa, lo correcto es cargar el fixture real en JSON y correr `fixtures`.
- `simulate-tournament` si usa Monte Carlo de verdad: en cada iteracion resuelve repechajes pendientes, simula la fase de grupos, selecciona los ocho mejores terceros, arma la llave y corre todo el knockout hasta la final.
- La asignacion de mejores terceros a cruces de primera ronda se resuelve con un algoritmo compatible con los grupos elegibles del cuadro oficial. Esa parte es una inferencia de modelado, no una copia textual de una matriz oficial cargada dentro del repo.
- `fixtures` ahora guarda automaticamente el estado en `runtime/tournament_state_2026.json` cuando encuentra partidos con `actual_score_a`, `actual_score_b` y `update_state: true`.
- `predict` usa ese estado automaticamente si no le pasas manualmente moral, tarjetas, puntos de grupo o diferencia de gol.
- Ese estado ya no solo cambia el contexto del partido: tambien altera la fuerza efectiva del equipo mediante Elo dinamico, forma, fatiga, disponibilidad y disciplina reciente.
- En knockout, `predict` ya modela empate en 90', proroga, probabilidad de penales y probabilidad total de clasificar.
- En knockout, el dashboard ya muestra tambien un marcador esperado de la tanda de penales y los resultados de penales mas probables.
- `sync_live_data_2026.py` ya mete clima por sede y, cuando el feed lo expone cerca del partido, odds de mercado como prior externo.
- El dataset ya trae `fifa_points`, `fifa_rank` y `fifa_country_code` oficiales; si quieres refrescarlos mas adelante, usa `sync_fifa_rankings.py`.
- Alineaciones confirmadas, cambios de XI, arbitro y bajas/ausencias estan preparados en modo best-effort: se cargan automaticamente si el feed publico los expone para ese partido.
- `sync_live_data_2026.py` tambien puede enriquecer partidos en vivo con un proveedor mas profundo de eventos y estadisticas. Si defines `API_FOOTBALL_KEY`, el pipeline intenta usar API-Football para lineups, eventos y stats live, manteniendo ESPN como base y fallback.
- La web ya muestra un mapa de proveedores para no depender solo de ESPN. El orden practico recomendado es: ESPN como fallback, API-Football como live profundo ya cableado, Sportmonks como segundo live profundo, The Odds API/OddsJam/Pinnacle/Betfair como mercado, NewsAPI/GDELT/fuentes oficiales como noticias, y Sportradar/Opta/Stats Perform como capa enterprise si hay contrato.
- La llave profunda publicada usa 100000 iteraciones como snapshot principal. El carril de 15000 queda solo como minimo tecnico para corridas rapidas u horarias cuando no conviene recalcular el snapshot profundo.
- La base histórica se reconstruye desde 1950 y exige al menos 25000 partidos oficiales cerrados. En el corte auditado contiene 29562 partidos oficiales con marcador válido; la definición excluye `Friendly` y `Unofficial Friendly`.
- Si un partido real se va a proroga o penales y lo marcas en el JSON, el estado acumula fatiga adicional y baja de disponibilidad para el siguiente partido.
- Si corriges un resultado viejo, lo correcto es ejecutar `state-reset` y luego volver a correr `fixtures` sobre el archivo completo en orden cronologico.
- Conviene poner un `id` estable en cada partido del JSON para que el script no aplique dos veces el mismo resultado.

## Auto-actualizacion cada 5 minutos en macOS

Hay cuatro archivos para dejar el modelo corriendo solo:

- `auto_update_quiniela.sh`: ejecuta `update` y luego regenera la llave actual.
- `com.jacquesbentata.quiniela2026.autoupdate.plist`: job de `launchd` con intervalo de 300 segundos.
- `install_launchd_quiniela.sh`: instala y activa el job.
- `uninstall_launchd_quiniela.sh`: lo desinstala.

Para instalarlo manualmente:

```bash
cd "/Users/jacquesbentata/Documents/New project"
chmod +x mundial_2026/auto_update_quiniela.sh mundial_2026/install_launchd_quiniela.sh mundial_2026/uninstall_launchd_quiniela.sh
./mundial_2026/install_launchd_quiniela.sh
```

Para quitarlo:

```bash
cd "/Users/jacquesbentata/Documents/New project"
./mundial_2026/uninstall_launchd_quiniela.sh
```

Los logs quedan en `mundial_2026/logs/`.

## Modo cloud para iPhone aunque tu Mac este apagada

Se dejo listo un workflow en:

- `.github/workflows/quiniela-pages.yml`

Y un empaquetador del sitio en:

- `mundial_2026/build_pages_site.sh`

Ese flujo:

1. sincroniza fixture/resultados/clima
2. usa ESPN como base y, si existe `API_FOOTBALL_KEY`, anade un feed live mas profundo
3. recompone el estado
4. recalcula la llave y el dashboard
5. publica un sitio estatico para abrirlo desde Safari en iPhone

Secrets/vars opcionales del workflow:

- `API_FOOTBALL_KEY`: API key del proveedor live profundo
- `API_FOOTBALL_BASE_URL`: override del endpoint base si lo necesitas
- `API_FOOTBALL_HOST`: host header del proveedor, por defecto `v3.football.api-sports.io`
- `SPORTMONKS_TOKEN`: sugerido como segundo proveedor live profundo; requiere implementar adaptador antes de que afecte el modelo.
- `THE_ODDS_API_KEY`: sugerido para consenso de mercado y lineas de goles; requiere adaptador.
- `NEWSAPI_KEY` o `GDELT_DOC_API`: sugeridos para noticias multi-fuente, lesiones y bajas; requieren adaptador y filtros.
- `SPORTRADAR_KEY` / `OPTA_KEY`: opciones enterprise si tienes contrato y SLA.

Archivos publicados en el sitio:

- `index.html`
- `dashboard_actual_2026.html`
- `reporte_actual_2026.md`
- `llave_actual_2026.md`
- `llave_actual_2026.json`
- `fixtures_live_2026.json`
- `scoreline_value_table.csv`
- `pick_decision_log.csv`
- `finished_match_audit.csv`
- `market_model_gap.csv`
- `model_change_log.csv`
- `MODEL_AUDIT.md`
- `VALIDATION_GATE.md`
- `ASSUMPTIONS.md`

Importante:

- GitHub Actions corre con cron cada 5 minutos, pero no tiene SLA duro; puede demorarse algunos minutos.
- Si quieres una cadencia realmente estricta aun con Mac apagada, lo correcto es migrarlo a un VPS o servidor dedicado.

## Auditoria y decision Penca

El modelo no promete acertar todos los marcadores exactos. La meta operativa es maximizar puntos esperados y no confundir probabilidad futbolistica con estrategia de Penca.

Nuevos artefactos clave:

- `scoreline_value_table.csv`: todos los marcadores 0-0 a 6-6 por partido, mas cola 7+/otro, con probabilidad, puntos esperados 8/5/3, ranking por probabilidad y ranking por valor Penca.
- `pick_decision_log.csv`: marcador modal del modelo, marcador recomendado para Penca, top 3 por probabilidad, top 3 por puntos esperados y razon si Penca no elige el modal.
- `finished_match_audit.csv`: compara partidos finalizados contra marcador modal y marcador Penca.
- `market_model_gap.csv`: deja preparada la comparacion contra mercado. Si no hay odds confiables, no inventa mercado y baja confianza.
- `model_change_log.csv`: registra cambios de auditoria/salida para no modificar pesos silenciosamente.

Reglas de lectura:

- Si `Marcador modelo` y `Marcador Penca` difieren, carga el de Penca salvo que el log marque warning fuerte.
- Una ablation con `matches=0` no vale como evidencia.
- Con menos de 30 partidos 2026 cerrados, Brier/log-loss del torneo son exploratorios.
- Una metrica 9/10 o 10/10 solo debe aparecer si hay muestra, benchmark y validacion suficiente.
