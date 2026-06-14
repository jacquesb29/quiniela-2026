# MODEL_AUDIT.md

Fecha de auditoría: 2026-06-13
Versión auditada: quiniela-2026 live, Monte Carlo 100k como snapshot profundo.

## Resumen ejecutivo

El proyecto ya separa dos capas que no deben mezclarse:

1. **Predicción futbolística**: calcula probabilidades reales, goles esperados y distribución de marcadores.
2. **Estrategia Penca**: usa esa distribución para maximizar puntos esperados bajo la regla 8/5/3.

La recomendación final para cargar en Penca debe salir de la segunda capa, no necesariamente del marcador modal del modelo. Esto explica casos como Corea del Sur 2-1 República Checa, donde el marcador modal era 1-1 pero la recomendación Penca 2-1 fue la decisión correcta.

## Módulos y archivos principales

- `modelo_quiniela_2026.py`: orquestador histórico del proyecto. Contiene funciones de expected goals, predicción por partido, distribución de marcador, Penca, auditoría y generación de dashboard. Sigue siendo el punto compatible principal.
- `worldcup2026/distributions.py`: motores de distribución de marcador, mezcla de modelos, baja anotación, sobredispersión y calibración de marcadores.
- `worldcup2026/models/expected_goals.py`: cálculo modular de goles esperados a partir de fuerza de equipo, contexto, estado y señales disponibles.
- `worldcup2026/dashboard/html_builder.py`: ensamblado visual del sitio.
- `worldcup2026/dashboard/backtesting.py`: resumen de desempeño contra partidos cerrados disponibles.
- `outputs/real_backtest/*.csv`: evidencia histórica anti-fuga disponible.
- `fixtures_live_2026.json`: fixtures, estado live/final y datos de partido.
- `llave_actual_2026.json`: llave proyectada publicada.
- `site/`: artefactos publicados por GitHub Pages.

## Dónde se calcula cada cosa

- Probabilidades 1X2: `predict_match()` y `predict_match_live()` agregan la distribución de marcadores en victoria local/equipo A, empate y victoria visitante/equipo B.
- Goles esperados: `expected_goals()` delega en `worldcup2026.models.expected_goals.expected_goals` y luego aplica ajustes prudentes de forma/escenario.
- Distribución de marcador: `build_model_stack()` y los modelos de `worldcup2026/distributions.py`.
- Simulación de torneo: funciones de Monte Carlo y llave alrededor de `simulate_tournament()` / generación de `llave_actual_2026.json`.
- Optimización Penca: `score_expected_points_for_penca()`, `penca_ovacion_score_options()` y `penca_ovacion_top_score()`.
- Auditoría finalizada: `finalized_score_audit()` compara marcador real contra marcador modal y recomendación Penca.
- Salida de decisión: `export_penca_decision_tables()` genera `scoreline_value_table.csv`, `pick_decision_log.csv`, `finished_match_audit.csv` y `market_model_gap.csv`.

## Hallazgos técnicos

- El modelo ya no debe leerse como Poisson puro. Hay Poisson, baja anotación, sobredispersión, ensamble, shape histórico y capa Penca.
- La distribución seguía siendo difícil de auditar por candidato. Se agregó `scoreline_value_table.csv` para cada marcador 0-0 a 6-6 más cola 7+/otro.
- La web podía sobrepremiar ablation aunque existiera una variante con `matches=0`. Se corrigió: una ablation con muestra cero es parcial/no válida y no puede justificar 9/10 o 10/10.
- El benchmark histórico muestra que el modelo completo debe tratar a Poisson simple como piso fuerte, no como rival ya superado. Si Poisson simple gana Brier/log-loss, el dashboard debe decir “medido, no superado”.
- La calibración histórica existe con muestra amplia, pero la calibración específica 2026 sigue provisional hasta alcanzar muestra mínima.
- Los índices de firmeza no son probabilidades de marcador exacto. La UI debe mantener esa distinción.

## Casos recientes

- México 2-0 Sudáfrica: modelo y Penca acertaron. No requiere ajuste manual.
- Corea del Sur 2-1 República Checa: el modal 1-1 falló, pero Penca 2-1 acertó. Reafirma que la decisión final debe leer la columna Penca.
- Canadá 1-1 Bosnia: modelo 1-0 y Penca 2-0 fallaron. Señal cualitativa para revisar empates en favoritos leves, no para parchear Bosnia/Canadá.
- Estados Unidos 4-1 Paraguay: modelo 1-0 y Penca 2-1 subestimaron cola ofensiva del favorito. Debe auditarse probabilidad previa de favorito por 3+ margen, 3+ goles y 4+ goles antes de calibrar.

## Riesgos de leakage

- No usar rankings, odds, lesiones, forma o plantillas conocidas después del kickoff.
- No usar resultados del mismo torneo para ajustar pesos manualmente.
- No rellenar variables faltantes con narrativa subjetiva.
- Si faltan odds o datos premium, el campo queda vacío/neutral y se registra warning.

## Variables redundantes o peligrosas

- `elo`, `fifa_rank`, `fifa_points`, `strength_index` y señales históricas pueden medir fuerza parecida. Deben controlarse por ablation y regularización.
- Variables narrativas como “momento”, “tapado” o “firmeza” no deben alterar lambdas si no tienen fuente trazable.
- Proxies de popularidad pública quedan desactivados hasta tener fuente real.

## Próximo trabajo estadístico

- Backtesting walk-forward con datos prepartido reales.
- Ablation real sin filas `matches=0`.
- Calibración específica de empates y goleadas con muestra suficiente.
- Comparación obligatoria contra mercado cuando existan odds prepartido confiables.
- Separación final de pesos congelados y estado live actualizable.
