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
- El modelo v1 queda congelado como baseline verificable en `modelo_quiniela_2026_v1_base.py`: commit `0370dfd`, SHA-256 `e49da3c5dc296d85c6de46529686bde9e2f1e3fa965dba843cb10d2fa0b05ad0`.
- El esquema `data/historical_match_master_schema.json` define la tabla maestra historica para backtesting sin fuga de informacion futura.
- El protocolo `data/prediction_operating_system_2026.json` define como usar el modelo durante el torneo: congelacion final, re-simulacion diaria, alertas, estrategia segun posicion en Penca y auditoria post-jornada.

## Como usarlo para la quiniela

- La web incluye una hoja de maxima certeza: ordena picks por solidez operativa, separa partidos trampa y marca cuando el marcador exacto es fragil.
- Usa la llave proyectada como mapa de escenarios, no como verdad fija. El ganador de cada cruce puede cambiar si cambia el rival que llega.
- Para picks de fase de grupos, separa partidos con favorito claro de partidos parejos. En partidos parejos conviene revisar empate, contexto de grupo y valor relativo de cuota/modelo.
- Para knockout, revisa siempre probabilidad de avanzar, marcador probable, prorroga y penales. No basta con ver "favorito".
- Si la web muestra "marcador del modelo" y "marcador Penca", usa el segundo para cargar la quiniela cuando difieran: el primero maximiza probabilidad futbolistica; el segundo maximiza puntos esperados bajo regla Penca.
- Antes de cerrar la quiniela, revisa bajas, alineaciones probables, portero titular y noticias de ultima hora.

## Riesgos residuales

- Sin `API_FOOTBALL_KEY`, el feed profundo se degrada al feed publico base. El in-play sigue funcionando, pero con menos detalle de eventos.
- Las probabilidades no deben forzarse artificialmente por encima de 90%. Una confianza alta solo es defendible si el partido realmente es desigual y los modelos coinciden.
- El modelo reduce ruido con 15000 iteraciones, pero no elimina incertidumbre de lesiones, rotaciones, tarjetas tempranas o goles accidentales.
- La mejor ventaja para la quiniela no es acertar todos los favoritos; es identificar donde el consenso esta sobrevalorando un favorito y donde conviene cubrir empate/upset.
- No se debe afirmar 90%-95% de acierto de marcador exacto unico: eso seria maquillaje estadistico. La cobertura alta se logra con multiples escenarios o reglas de cobertura, no con un solo marcador.

## Guardrails agregados

- Tests de integridad del sorteo final y clasificados.
- Tests para evitar volver a publicar una llave de smoke test con pocas iteraciones.
- Tests del workflow de Pages: cron cada 5 minutos, 15000 simulaciones, `API_FOOTBALL_KEY` y deploy sin cancelar corridas previas.
- Tests de estado live/final para que el in-play no falle por diferencias de nombre entre proveedores.
- Tests del baseline v1 congelado y del esquema historico anti-fuga.
- Tests del sistema operativo de prediccion para no cambiar pesos durante el Mundial ni crear un final pre-torneo antes de validar.
- Separacion metodologica entre modelo pre-torneo, modelo pre-partido y modelo live.
- Separacion entre prediccion futbolistica y optimizacion Penca.
