# QUINIELA_OPERATION_GUIDE — Cómo operar el sistema

Guía práctica para usar el modelo + la capa Mercado/T-60 en cada jornada. El
modelo está **congelado y validado** (ver `MODEL_LOCK.md`); esta guía es operativa.

## 1. Predecir un partido con el modelo
```bash
python3 mundial_2026/modelo_quiniela_2026.py predict "España" "Uruguay" --show-factors
python3 mundial_2026/modelo_quiniela_2026.py predict "Mexico" "Morocco" --neutral --monte-carlo 15000 --seed 7
```
La web/llave se regeneran con el flujo habitual del proyecto (dashboard, `build_pages_site.sh`).

## 2. Validación final (opcional, reproducible)
```bash
python3 run_final_validation.py      # corre tests + todos los runners de auditoría
```
Salidas: `outputs/final/final_validation_summary.json` y `.md`.

## 3. Flujo Mercado/T-60 antes de cada partido
### 3.1 Cargar odds manualmente — `data/market_odds_input.csv`
Obligatorios: `match_id, kickoff_utc, captured_at_utc, snapshot_type, source, odds_format` + 1X2 completo (`odds_home/draw/away`). Reglas:
- `captured_at_utc` **anterior** a `kickoff_utc`.
- `snapshot_type` = `opening`/`t60`/`closing`; **closing NO decide** (solo auditoría).
- No inventar odds; lo que falte se deja vacío.

### 3.2 Cargar T-60 — `data/t60_inputs.csv`
`match_id, captured_at_utc, lineup_confirmed, lineup_changes, injuries_confirmed, starting_gk, gk_changed, notes` (solo datos confirmados).

### 3.3 Correr el pipeline
```bash
python3 run_market_t60_pipeline.py
```
Falla claro si falta `data/market_odds_input.csv`; no se rompe si no hay mercado.

## 4. Qué archivos revisar
- `outputs/market/market_implied_probabilities.csv` — odds sin vig + total/supremacía/λ.
- `outputs/market/market_model_gap.csv` — gap 1X2 (TV), total, supremacía, contradicción, severidad.
- `outputs/market/market_decision_log.csv` — `final_pick`, `action`, `confidence_label`.
- `outputs/market/t60_decision_log.csv` — `pick_before/after`, `changed`, `trigger`, `reason`.
- `outputs/market/market_dashboard.html` — vista por partido (abrir en navegador).

## 5. Cómo interpretar
- **Pick modelo:** la predicción del modelo (1X2/marcador) sin mercado.
- **Pick mercado:** el favorito implícito por las odds sin vig (solo si hay 1X2).
- **Pick final:** la recomendación operativa tras la regla de decisión.
- **Confidence:** `Alta` (modelo y mercado coinciden, gap bajo) · `Media` (gap moderado o sin mercado) · `Baja` (gap fuerte o contradicción). **Nunca subir a Alta a mano.**

Acciones:
- **trust_model** — modelo y mercado coinciden, gap bajo → usar pick del modelo (puede ser Alta).
- **keep_pick** — mismo ganador, gap moderado → pick del modelo, confianza ≤ Media.
- **shade_to_market** — mismo ganador, gap fuerte sin razón trazable → pick del modelo pero acercarse al mercado; Baja.
- **lower_confidence** — gap fuerte con razón trazable → pick del modelo, Baja.
- **follow_market** — el mercado contradice al modelo en el ganador → seguir al mercado; Baja.
- **no_market_available** — sin 1X2 de mercado → usar pick del modelo; confianza ≤ Media.

T-60:
- **changed=True** — el pick se actualizó por **razón material** (contradicción fuerte, movimiento de odds, alineación inesperada, baja, cambio de portero). Revisar `pick_before → pick_after` y `reason`.
- **changed=False** — el pick se **mantuvo** (sin razón material, sin odds válidas o closing rechazado). No se fuerza nada.

## 6. Reglas de uso (no maquillar)
- El track de mercado 2026 es **exploratorio** (n<30): recomendaciones operativas, no validación.
- No mostrar "Alta" si la decisión dice "Baja".
- No usar `closing`/odds post-kickoff para decidir.
- El modelo está congelado; no cambiar pesos/flags sin un nuevo gate (`MODEL_LOCK.md`).
