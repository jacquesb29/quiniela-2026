# Auditoria de quiniela - Mundial 2026

Fecha de auditoria: 2026-05-15.

## Estado validado

- El sorteo usado por el modelo contiene 12 grupos, 48 selecciones y 48 nombres unicos.
- Todos los equipos del sorteo existen en `teams_2026.json` y tienen `status = qualified`.
- Bosnia and Herzegovina, Dem. Rep. of Congo e Iraq estan incluidos como clasificados.
- Italy, Jamaica, Bolivia, Suriname y New Caledonia no aparecen en el sorteo final.
- La llave publicada usa al menos 15000 simulaciones Monte Carlo.
- GitHub Actions reconstruye el dashboard cada 5 minutos y tambien en cada push a `main`.
- El dashboard acepta variantes de estado en vivo del proveedor (`in`, `live`, `in_progress`) y de partido final (`post`, `final`, `finished`).

## Como usarlo para la quiniela

- Usa la llave proyectada como mapa de escenarios, no como verdad fija. El ganador de cada cruce puede cambiar si cambia el rival que llega.
- Para picks de fase de grupos, separa partidos con favorito claro de partidos parejos. En partidos parejos conviene revisar empate, contexto de grupo y valor relativo de cuota/modelo.
- Para knockout, revisa siempre probabilidad de avanzar, marcador probable, prorroga y penales. No basta con ver "favorito".
- Antes de cerrar la quiniela, revisa bajas, alineaciones probables, portero titular y noticias de ultima hora.

## Riesgos residuales

- Sin `API_FOOTBALL_KEY`, el feed profundo se degrada al feed publico base. El in-play sigue funcionando, pero con menos detalle de eventos.
- Las probabilidades no deben forzarse artificialmente por encima de 90%. Una confianza alta solo es defendible si el partido realmente es desigual y los modelos coinciden.
- El modelo reduce ruido con 15000 iteraciones, pero no elimina incertidumbre de lesiones, rotaciones, tarjetas tempranas o goles accidentales.
- La mejor ventaja para la quiniela no es acertar todos los favoritos; es identificar donde el consenso esta sobrevalorando un favorito y donde conviene cubrir empate/upset.

## Guardrails agregados

- Tests de integridad del sorteo final y clasificados.
- Tests para evitar volver a publicar una llave de smoke test con pocas iteraciones.
- Tests del workflow de Pages: cron cada 5 minutos, 15000 simulaciones, `API_FOOTBALL_KEY` y deploy sin cancelar corridas previas.
- Tests de estado live/final para que el in-play no falle por diferencias de nombre entre proveedores.
