# Modelo probabilistico para quiniela del Mundial 2026

Este modulo deja una base reproducible para predecir marcadores y probabilidades de clasificacion de cara al Mundial 2026.
La nueva version ya incorpora variables macro, historicas, tacticas, disciplinares y de plantilla, usando proxies cuando el dato exacto no esta disponible.

## Que modela

- Fuerza base por seleccion usando Elo internacional.
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
- Distribucion exacta de marcadores con Poisson bivariante.

## Cobertura inicial de datos

- Fecha de corte: 16 de marzo de 2026.
- 42 clasificados confirmados.
- 16 selecciones en repechaje UEFA por 4 cupos.
- 6 selecciones en repechaje FIFA por 2 cupos.

## Archivos

- `teams_2026.json`: dataset base de selecciones y rating Elo.
- `modelo_quiniela_2026.py`: CLI para prediccion, perfiles internos y simulacion Monte Carlo del torneo.
- `fixtures_template.json`: ejemplo de formato para cargar partidos con estado dinamico.
- `tournament_2026_draw.json`: draw oficial del Mundial 2026 con placeholders de repechaje.
- `tournament_state_2026.json`: estado persistente que el modelo actualiza automaticamente entre ejecuciones.

Solo se ejecuta `modelo_quiniela_2026.py`. Los archivos `.json` no se ejecutan: se usan como entradas o como estado guardado.

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
python3 mundial_2026/modelo_quiniela_2026.py predict "España" Uruguay --monte-carlo 10000 --seed 7
```

Predecir un partido de eliminacion directa con prorroga y penales:

```bash
python3 mundial_2026/modelo_quiniela_2026.py predict "España" Uruguay --stage round16 --monte-carlo 10000 --seed 7
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
python3 mundial_2026/modelo_quiniela_2026.py playoffs --iterations 10000
```

Simular el torneo completo con Monte Carlo:

```bash
python3 mundial_2026/modelo_quiniela_2026.py simulate-tournament --iterations 10000 --top 20
```

Simular el torneo completo usando el draw oficial incluido:

```bash
python3 mundial_2026/modelo_quiniela_2026.py simulate-tournament \
  --config mundial_2026/tournament_2026_draw.json \
  --iterations 10000 \
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

## Notas

- Esta version no intenta decir que ya existen los 48 participantes finales: al 16 de marzo de 2026 todavia faltan por definirse 6 cupos.
- Si quieres afinar el modelo, la mejora mas fuerte es reemplazar los proxies por datos reales de convocatorias finales, xG, cargas fisicas, entrenadores confirmados, tarjetas acumuladas y estadisticas por jugador.
- Las variables de jugadores estan modeladas con una plantilla proxy reproducible cuando no hay lista real; si agregas `players` por equipo en `teams_2026.json`, el modelo puede usar esos valores en lugar de las estimaciones.
- Para una quiniela completa, lo correcto es cargar el fixture real en JSON y correr `fixtures`.
- `simulate-tournament` si usa Monte Carlo de verdad: en cada iteracion resuelve repechajes pendientes, simula la fase de grupos, selecciona los ocho mejores terceros, arma la llave y corre todo el knockout hasta la final.
- La asignacion de mejores terceros a cruces de primera ronda se resuelve con un algoritmo compatible con los grupos elegibles del cuadro oficial. Esa parte es una inferencia de modelado, no una copia textual de una matriz oficial cargada dentro del repo.
- `fixtures` ahora guarda automaticamente el estado en `tournament_state_2026.json` cuando encuentra partidos con `actual_score_a`, `actual_score_b` y `update_state: true`.
- `predict` usa ese estado automaticamente si no le pasas manualmente moral, tarjetas, puntos de grupo o diferencia de gol.
- Ese estado ya no solo cambia el contexto del partido: tambien altera la fuerza efectiva del equipo mediante Elo dinamico, forma, fatiga, disponibilidad y disciplina reciente.
- En knockout, `predict` ya modela empate en 90', proroga, probabilidad de penales y probabilidad total de clasificar.
- En knockout, el dashboard ya muestra tambien un marcador esperado de la tanda de penales y los resultados de penales mas probables.
- `sync_live_data_2026.py` ya mete clima por sede y, cuando el feed lo expone cerca del partido, odds de mercado como prior externo.
- Alineaciones confirmadas, cambios de XI, arbitro y bajas/ausencias estan preparados en modo best-effort: se cargan automaticamente si el feed publico los expone para ese partido.
- La llave publicada en el dashboard cloud ahora usa 1200 iteraciones por defecto para reducir ruido Monte Carlo frente a 300.
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
2. recompone el estado
3. recalcula la llave y el dashboard
4. publica un sitio estatico para abrirlo desde Safari en iPhone

Archivos publicados en el sitio:

- `index.html`
- `dashboard_actual_2026.html`
- `reporte_actual_2026.md`
- `llave_actual_2026.md`
- `llave_actual_2026.json`
- `fixtures_live_2026.json`

Importante:

- GitHub Actions corre con cron cada 5 minutos, pero no tiene SLA duro; puede demorarse algunos minutos.
- Si quieres una cadencia realmente estricta aun con Mac apagada, lo correcto es migrarlo a un VPS o servidor dedicado.
