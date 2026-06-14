# Runbook operativo — Mercado y T-60 (F1)

Guía para usar el flujo de mercado/T-60 **antes de cada partido**. Este flujo
**no toca el modelo** (pesos, lambdas, metodología, Penca): solo carga odds
manuales, las convierte sin vig, las compara con el modelo, decide una
recomendación operativa y la muestra. El track de mercado 2026 es **exploratorio**
(n<30): son recomendaciones operativas, no validación estadística.

---

## 1. Archivos manuales que debo llenar

Solo dos, ambos en `data/`:

- `data/market_odds_input.csv` — **crítico**. Odds prepartido por partido.
- `data/t60_inputs.csv` — opcional pero recomendado. Alineación/bajas/portero a T-60.

> Regla absoluta: **no inventar odds**, **no scraping**, **no autocompletar**. Si
> no tienes un dato, deja la celda vacía.

---

## 2. Cómo llenar `data/market_odds_input.csv`

Columnas (orden fijo):
```
match_id, kickoff_utc, captured_at_utc, snapshot_type, source, odds_format,
odds_home, odds_draw, odds_away,
total_line, odds_over, odds_under,
handicap_line, odds_hcap_home, odds_hcap_away,
tt_home_line, odds_tt_home_over, odds_tt_home_under,
tt_away_line, odds_tt_away_over, odds_tt_away_under,
note
```

Campos **obligatorios** (si faltan, la fila se descarta con log):
- `match_id`: `YYYYMMDD_EquipoA_vs_EquipoB` (espacios → `_`; el **primer** equipo es el lado *home*/A, que debe coincidir con `odds_home`).
- `kickoff_utc`, `captured_at_utc`: ISO-8601 con zona (`2026-06-12T19:00:00Z`).
- `snapshot_type`: `opening` | `t60` | `closing`.
- `source`: trazable (`manual:pinnacle`, `the_odds_api`, …).
- `odds_format`: `decimal` | `american` | `fractional`.

Mercado mínimo utilizable = **1X2 completo** (`odds_home`,`odds_draw`,`odds_away`).
Los demás bloques (over/under, handicap, team totals) son opcionales; cada bloque
de dos vías debe tener **ambos lados** o ninguno.

Reglas de cuota:
- Decimal `≤ 1.0` es inválida.
- American: `+150`→2.50, `-200`→1.50 (positivos sin `+` también valen, p.ej. `250`).
- Fractional: `5/2`→3.50.

### Cómo evitar closing / post-kickoff
- `captured_at_utc` **debe ser anterior** a `kickoff_utc`. Una captura posterior se
  rechaza para decisión (anti-leakage).
- `snapshot_type=closing` **no decide** (solo auditoría/CLV). Para decidir usa
  `opening` o `t60`.
- Para la actualización final, usa `snapshot_type=t60` capturado ~60' antes.

---

## 3. Cómo llenar `data/t60_inputs.csv`

Columnas:
```
match_id, captured_at_utc, lineup_confirmed, lineup_changes,
injuries_confirmed, starting_gk, gk_changed, notes
```
- `match_id`: igual al de odds.
- `lineup_confirmed`: `true`/`false`. `lineup_changes`: entero (nº de cambios vs XI esperado).
- `injuries_confirmed`: lista separada por `;` (vacío si no hay).
- `starting_gk`: portero titular; `gk_changed`: `true`/`false`.
- `notes`: texto libre.

Las odds del partido se enlazan automáticamente desde `market_odds_input.csv`
(prefiere `t60` sobre `opening`).

---

## 4. Qué fuentes usar

- Odds: casa de apuestas o agregador confiable (Pinnacle, The Odds API, etc.).
  Anota la fuente en `source`. No mezclar `snapshot_type` distintos en una fila.
- Alineaciones/bajas/portero: parte oficial del equipo / fuentes confirmadas.
  Solo cargar lo **confirmado**; rumores no entran.

---

## 5. Comandos a ejecutar (en orden)

Forma recomendada (un solo comando que corre todo):
```bash
python3 run_market_t60_pipeline.py
```

Equivale a, en este orden:
```bash
python3 -m worldcup2026.market.build_market_implied     # 1) odds -> sin vig
python3 build_market_model_gap.py                       # 2) modelo vs mercado
python3 build_market_decisions.py                       # 3) decisión
python3 run_t60_update.py                               # 4) T-60 (si hay t60_inputs.csv)
python3 build_market_dashboard.py                       # 5) dashboard HTML
```

El pipeline **falla claramente** si falta `data/market_odds_input.csv` y **no se
rompe** si no hay mercado usable (genera secciones "sin mercado/pendiente").

---

## 6. Qué outputs revisar

- `outputs/market/market_implied_probabilities.csv` — odds sin vig + total/supremacía/lambdas.
- `outputs/market/market_model_gap.csv` — gap 1X2 (TV), total, supremacía, contradicción, severidad.
- `outputs/market/market_decision_log.csv` — `final_pick`, `action`, `confidence_label`.
- `outputs/market/t60_decision_log.csv` — `pick_before/after`, `changed`, `trigger`, `reason`.
- `outputs/market/last_hour_update.csv` — estado de odds/alineación/portero a T-60.
- `outputs/market/market_dashboard.html` — vista por partido (abrir en navegador).

---

## 7. Cómo interpretar

Acciones (`market_decision_log.csv` / dashboard):
- **trust_model**: modelo y mercado coinciden y el gap es bajo → usar el pick del modelo (puede ser confianza Alta).
- **shade_to_market**: mismo ganador pero gap fuerte sin razón trazable → el pick sigue siendo el del modelo, pero conviene acercarse al mercado; confianza Baja.
- **no_market_available**: no hay mercado 1X2 usable → se mantiene el pick del modelo; confianza nunca Alta.
- **follow_market**: el mercado contradice al modelo en el ganador → la recomendación sigue al mercado; confianza Baja.
- **keep_pick**: mismo ganador, gap moderado → se conserva el pick del modelo; confianza máxima Media.
- **lower_confidence**: gap fuerte con razón trazable → se mantiene el pick del modelo con confianza Baja.

Confianza:
- **Alta**: modelo y mercado alineados de cerca. Solo posible con mercado y gap bajo.
- **Media**: gap moderado o sin mercado.
- **Baja**: gap fuerte o contradicción de ganador. **Nunca** subir a Alta manualmente.

T-60 `changed`:
- **changed=True**: el pick se actualizó por una **razón material** (contradicción
  fuerte, movimiento de odds, alineación inesperada, baja, cambio de portero, gap
  fuerte). Revisa `pick_before → pick_after` y `reason`.
- **changed=False**: el pick se **mantuvo** (sin razón material, sin odds válidas, o
  closing rechazado). No se fuerza ningún cambio.

---

## 8. Qué NO hacer

- No editar el modelo, pesos, lambdas, metodología ni Penca.
- No inventar odds ni autocompletar las faltantes; no scraping.
- No usar `closing`/capturas post-kickoff para decidir.
- No mostrar "Alta" si la decisión dice "Baja"; no maquillar.
- No tratar el track 2026 de mercado como validación: es exploratorio (n<30).
