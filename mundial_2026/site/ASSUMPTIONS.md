# ASSUMPTIONS.md

Supuestos usados cuando faltan datos externos confirmados.

1. Regla Penca/Ovación aproximada: 8 puntos por marcador exacto, 5 por diferencia correcta y 3 por resultado correcto.
2. Si no hay odds confiables prepartido, `market_model_gap.csv` deja mercado vacío y registra warning; no se inventa mercado.
3. Si no hay proveedor live profundo, el modelo usa scoreboard base, estado de partido, noticias abiertas y datos históricos disponibles.
4. La llave 100k es snapshot profundo; el carril live de 5 minutos actualiza dashboard/estado y usa la última llave profunda disponible hasta la siguiente corrida profunda.
5. Variables faltantes de FIFA histórico, mercado histórico, plantillas históricas o lesiones históricas quedan neutras; no se rellenan con proxies narrativos.
6. Los índices de firmeza son índices de decisión, no probabilidades reales de marcador exacto.
7. Las recomendaciones Penca pueden diferir del marcador modal si maximizan puntos esperados bajo 8/5/3.
8. LOCK_TOURNAMENT y NO_OVERREACTION se asumen activos durante el torneo.
