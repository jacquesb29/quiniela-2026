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

## Issues técnicos

- **Bug de caché mutable — RESUELTO.** En `worldcup2026/distributions.py` los
  wrappers de distribución (`independent_score_distribution`,
  `score_distribution`, `overdispersed_score_distribution`,
  `cached_low_score_distribution`) devolvían el dict cacheado por `@lru_cache`, y
  consumidores como `low_score_adjusted_distribution` y el cuerpo de
  `cached_low_score_distribution` lo mutaban in-place. Eso corrompía el caché de
  `cached_independent_score_distribution` y, dentro de cada predicción, pisaba el
  miembro "Poisson independiente" con la distribución de baja anotación, dejando
  `predict_match` no determinista y dependiente del orden de llamadas.
  **Corrección (solo reproducibilidad, sin tocar pesos/lambdas/metodología/Penca):**
  cada wrapper devuelve ahora una copia defensiva del dict cacheado y la función
  cacheada de baja anotación se separó en interna (`_cached_low_score_distribution_inner`)
  + wrapper que copia. `predict_match` es determinista; el adaptador de backtest
  ya no fuerza caché frío. Efecto en métricas: estable (Δbrier ≈ −0.00002,
  Δlog-loss ≈ −0.00023), consecuencia de restaurar el miembro "contrast", no de
  ajuste predictivo.
- **Procedencia de `elo_*_pre` (F0.4b) — RESUELTO.** Auditoría de código de
  `tools/build_real_historical_backtest.py`: ordena por fecha, registra
  `elo_*_pre` ANTES del partido y `update_elo` solo DESPUÉS; equipos nuevos en
  1500; sin rankings ni resultados posteriores → walk-forward por construcción.
  Verificación independiente (`worldcup2026/elo_rederive.py`): una re-derivación
  walk-forward propia reproduce el Elo almacenado con pearson = 1.000000 y
  diferencia máxima 0.0005 puntos (solo redondeo a 3 decimales). El backtest con
  Elo re-derivado es idéntico al original (shift de log-loss 0.000000) y sigue
  superando a Poisson/Elo. **Sin evidencia de fuga → `leakage_warning=False`.**
  Artefactos: `outputs/walk_forward/rederived_elo_matches.csv`,
  `elo_leakage_audit.csv`, `elo_leakage_audit.md`.

## Estado de validación (F0.3 / F0.4 / F0.5)

- Comparación pareada honesta en `outputs/real_backtest/paired_comparison.csv`:
  el modelo supera a `poisson_simple` y `elo_puro` en log-loss sobre la misma
  población (n=1930). `mercado_puro` queda `sin_muestra` (0 odds históricas), no
  "no superado".
- **Walk-forward (F0.4)** en `outputs/walk_forward/`: 8 folds expanding
  (min_train=400, step=200), 1520 partidos de test, anti-leakage estricto
  (`train_end_date < test_start_date` por fold). Out-of-sample el modelo supera a
  Poisson simple y Elo puro en log-loss (≈0.9950 vs 1.0059 y 1.0035; `beats=True`
  en agregado y en 6/8 folds — pierde solo en los dos folds más antiguos
  1970s–80s). `exact_score_accuracy ≈ 0.14`, Penca medio ≈ 2.5 pts/partido.
- Cobertura de mercado: 0/1930. Sin odds prepartido históricas no se compara
  contra mercado.
- **Etiqueta vigente (`outputs/validation_status.json`): `validado`.** Se cumplen
  los cuatro gates: n≥500 (1520 de walk-forward), comparación out-of-sample,
  supera benchmarks comparables (Poisson y Elo) y sin advertencia de leakage
  (Elo verificado en F0.4b). Alcance del término: validado **fuera de muestra
  contra Poisson/Elo en histórico de Mundial/Euro/Copa América**; NO implica
  comparación contra mercado (sin odds históricas) ni que las variables no-Elo
  aporten señal (históricamente quedan neutras). Matiz por fold: el modelo gana
  en 6/8 folds y pierde en los dos más antiguos (1970s–80s).
