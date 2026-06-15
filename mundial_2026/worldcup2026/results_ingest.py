"""Ingesta de resultados 2026 — feed primario, CSV de fallback.

Fuente PRIMARIA: ``fixtures_live_2026.json`` (el feed más actualizado disponible).
Fuente de FALLBACK: ``finished_match_audit.csv`` (artefacto derivado del dashboard),
usado SOLO si el feed falta/ilegible o no tiene partidos finalizados.

Reglas:
- No inventa resultados: un partido cuenta como finalizado únicamente si trae
  marcador real (``actual_score_a`` y ``actual_score_b`` no nulos).
- No depende de re-ejecutar el dashboard.
- Módulo liviano: NO importa el monolito (la predicción vive en
  ``worldcup2026.live_prediction``), para que los tests lo importen rápido.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "fixtures_live_2026.json"
AUDIT_CSV_PATH = ROOT / "finished_match_audit.csv"
HISTORICAL_CSV_PATH = ROOT / "data" / "historical_matches.csv"

DATA_INVENTORY_MD = ROOT / "outputs" / "audit" / "worldcup2026_data_inventory.md"
SOURCE_CONSISTENCY_CSV = ROOT / "outputs" / "audit" / "worldcup2026_source_consistency.csv"

# Estados espejo del monolito (normalized_match_status_state).
LIVE_STATUS_STATES = {"in", "live", "in_progress", "in-progress", "halftime",
                      "half_time", "half-time", "ht", "extra_time", "extra-time",
                      "et", "penalties", "shootout"}
FINAL_STATUS_STATES = {"post", "final", "finished", "full_time", "full-time",
                       "ft", "aet", "after_extra_time", "after-extra-time",
                       "penalties_final", "after_penalties", "after-penalties"}
PENDING_STATUS_STATES = {"pre", "scheduled", "ns", "upcoming", "not_started", "", "none"}

# Buckets explícitos solicitados para la auditoría de status.
STATUS_BUCKETS = ("pre", "live", "post", "final", "finished", "ft", "other")


def normalized_status_state(status_state: Optional[str]) -> str:
    s = str(status_state or "").strip().lower()
    if s in LIVE_STATUS_STATES:
        return "live"
    if s in FINAL_STATUS_STATES:
        return "final"
    return "pending"


def has_final_score(fx: dict) -> bool:
    """Único criterio de finalizado: marcador real presente. No inventa nada."""
    return fx.get("actual_score_a") is not None and fx.get("actual_score_b") is not None


def title_of(fx: dict) -> str:
    return f"{fx.get('team_a')} vs {fx.get('team_b')}"


# --------------------------------------------------------------------------- #
# Carga de fuentes
# --------------------------------------------------------------------------- #
def load_fixtures(path: Path = FIXTURES_PATH) -> Optional[List[dict]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def load_audit_csv(path: Path = AUDIT_CSV_PATH) -> List[dict]:
    if not path.exists():
        return []
    try:
        return list(csv.DictReader(path.open(encoding="utf-8")))
    except OSError:
        return []


def finalized_fixtures(fixtures: List[dict]) -> List[dict]:
    return [f for f in fixtures if has_final_score(f)]


def _latest_finalized_date(fixtures: List[dict]) -> str:
    dates = [(f.get("kickoff_utc") or "")[:10] for f in finalized_fixtures(fixtures)]
    dates = [d for d in dates if d]
    return max(dates) if dates else "n/d"


# --------------------------------------------------------------------------- #
# Staleness: feed vs CSV derivado
# --------------------------------------------------------------------------- #
def compute_staleness(fixtures: Optional[List[dict]], audit_rows: List[dict]) -> dict:
    feed_fin = {}
    for f in finalized_fixtures(fixtures or []):
        feed_fin[title_of(f)] = f"{int(f['actual_score_a'])}-{int(f['actual_score_b'])}"
    csv_fin = {r.get("title"): r.get("actual_score") for r in audit_rows}
    only_feed = sorted(set(feed_fin) - set(csv_fin))
    only_csv = sorted(set(csv_fin) - set(feed_fin))
    mismatch = sorted(t for t in (set(feed_fin) & set(csv_fin)) if feed_fin[t] != csv_fin[t])
    return {
        "feed_finalized": len(feed_fin),
        "csv_finalized": len(csv_fin),
        "only_in_feed": only_feed,
        "only_in_csv": only_csv,
        "score_mismatch": mismatch,
        "csv_is_stale_vs_feed": bool(only_feed or only_csv or mismatch),
    }


# --------------------------------------------------------------------------- #
# Selección de fuente
# --------------------------------------------------------------------------- #
@dataclass
class ResultsSource:
    source: str
    mode: str  # "feed" | "fallback_csv"
    fixtures: List[dict] = field(default_factory=list)     # finalizados (modo feed)
    audit_rows: List[dict] = field(default_factory=list)   # filas CSV (modo fallback)
    total_matches: int = 0
    finalized_matches: int = 0
    latest_date: str = "n/d"
    staleness: dict = field(default_factory=dict)
    feed_available: bool = False
    fallback_reason: str = ""


def load_results_source(fixtures_path: Path = FIXTURES_PATH,
                        audit_path: Path = AUDIT_CSV_PATH,
                        prefer_feed: bool = True) -> ResultsSource:
    fixtures = load_fixtures(fixtures_path)
    audit_rows = load_audit_csv(audit_path)
    feed_available = fixtures is not None
    staleness = compute_staleness(fixtures, audit_rows)

    if prefer_feed and feed_available:
        fin = finalized_fixtures(fixtures)
        if fin:
            return ResultsSource(
                source=fixtures_path.name, mode="feed", fixtures=fin,
                total_matches=len(fixtures), finalized_matches=len(fin),
                latest_date=_latest_finalized_date(fixtures), staleness=staleness,
                feed_available=True)
        if not audit_rows:
            # Feed presente pero aún sin finalizados, y no hay CSV: feed sigue siendo primario.
            return ResultsSource(
                source=fixtures_path.name, mode="feed", fixtures=[],
                total_matches=len(fixtures), finalized_matches=0,
                latest_date="n/d", staleness=staleness, feed_available=True)
        # Feed sin finalizados pero el CSV tiene datos -> fallback para no perder resultados.
        reason = "feed presente pero sin partidos finalizados; se usa CSV como respaldo"
    else:
        reason = "feed ausente o ilegible; se usa CSV como respaldo"

    return ResultsSource(
        source=audit_path.name, mode="fallback_csv", audit_rows=audit_rows,
        total_matches=len(audit_rows), finalized_matches=len(audit_rows),
        latest_date="n/d", staleness=staleness, feed_available=feed_available,
        fallback_reason=reason)


def finalized_records(src: ResultsSource) -> List[dict]:
    """Registros canónicos de partidos finalizados, agnósticos del modelo."""
    recs: List[dict] = []
    if src.mode == "feed":
        for f in sorted(src.fixtures, key=lambda x: (x.get("kickoff_utc") or "")):
            aa, ab = int(f["actual_score_a"]), int(f["actual_score_b"])
            recs.append({
                "title": title_of(f), "team_a": f["team_a"], "team_b": f["team_b"],
                "actual_score_a": aa, "actual_score_b": ab, "actual_score": f"{aa}-{ab}",
                "date": (f.get("kickoff_utc") or "")[:10] or "n/d",
                "stage": f.get("stage", ""), "status_state": f.get("status_state"),
                "status_detail": f.get("status_detail"), "fixture": f, "from_fallback": False,
            })
    else:
        for r in src.audit_rows:
            recs.append({
                "title": r.get("title"), "actual_score": r.get("actual_score"),
                "model_score": r.get("model_score"), "penca_score": r.get("penca_score"),
                "model_points": float(r.get("model_points") or 0.0),
                "penca_points": float(r.get("penca_points") or 0.0),
                "date": "n/d", "stage": "", "status_state": "n/d", "status_detail": "n/d",
                "fixture": None, "from_fallback": True,
            })
    return recs


# --------------------------------------------------------------------------- #
# Auditoría de valores de status
# --------------------------------------------------------------------------- #
def status_value_audit(fixtures: List[dict]):
    """Cuenta status_state en buckets explícitos + FT desde status_detail."""
    buckets = {k: 0 for k in STATUS_BUCKETS}
    other_values: dict = {}
    ft_detail = 0
    for f in fixtures:
        ss = str(f.get("status_state") or "").strip().lower()
        if ss in ("", "none"):
            buckets["pre"] += 1  # sin estado explícito = aún no jugado
        elif ss in ("pre", "live", "post", "final", "finished"):
            buckets[ss] += 1
        else:
            buckets["other"] += 1
            other_values[ss] = other_values.get(ss, 0) + 1
        if str(f.get("status_detail") or "").strip().upper() == "FT":
            ft_detail += 1
    buckets["ft"] = ft_detail  # 'FT' proviene de status_detail, no de status_state
    return buckets, other_values


# --------------------------------------------------------------------------- #
# Reportes (puros, sin modelo)
# --------------------------------------------------------------------------- #
def _historical_summary() -> dict:
    rows = load_audit_csv(HISTORICAL_CSV_PATH)
    if not rows:
        return {"total": 0, "finalized": 0, "latest": "n/d", "y2026": 0}
    dates = sorted(str(r.get("date") or "") for r in rows)
    y2026 = sum(1 for r in rows if str(r.get("date") or "").startswith("2026"))
    return {"total": len(rows), "finalized": len(rows),
            "latest": dates[-1] if dates else "n/d", "y2026": y2026}


def write_source_consistency(out_path: Path = SOURCE_CONSISTENCY_CSV) -> List[dict]:
    fixtures = load_fixtures() or []
    audit_rows = load_audit_csv()
    stale = compute_staleness(fixtures, audit_rows)
    hist = _historical_summary()
    feed_fin = finalized_fixtures(fixtures)

    rows = [
        {"source": "fixtures_live_2026.json",
         "total_matches": len(fixtures),
         "finalized_matches": len(feed_fin),
         "latest_date": _latest_finalized_date(fixtures),
         "notes": "FUENTE PRIMARIA: feed directo 2026; criterio finalizado = actual_score no nulo"},
        {"source": "finished_match_audit.csv",
         "total_matches": len(audit_rows),
         "finalized_matches": len(audit_rows),
         "latest_date": "n/d (el CSV no guarda fecha)",
         "notes": "FALLBACK: derivado del dashboard; " +
                  ("DESACTUALIZADO vs feed" if stale["csv_is_stale_vs_feed"] else "sincronizado con el feed")},
        {"source": "data/historical_matches.csv",
         "total_matches": hist["total"],
         "finalized_matches": hist["finalized"],
         "latest_date": hist["latest"],
         "notes": f"Histórico F3/F7 (1950→{hist['latest']}); partidos 2026 = {hist['y2026']} (no se usa para 2026)"},
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["source", "total_matches", "finalized_matches",
                                          "latest_date", "notes"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


def write_data_inventory(out_path: Path = DATA_INVENTORY_MD) -> str:
    src = load_results_source()
    fixtures = load_fixtures() or []
    buckets, other = status_value_audit(fixtures)
    recs = finalized_records(src)
    excluded = [f for f in fixtures if not has_final_score(f)]

    L = [
        "# Inventario de datos 2026", "",
        f"- **Fuente principal usada:** `{src.source}` (modo `{src.mode}`).",
    ]
    if src.fallback_reason:
        L.append(f"- **Motivo de fallback:** {src.fallback_reason}.")
    L += [
        f"- **Partidos totales:** {src.total_matches}.",
        f"- **Partidos finalizados:** {src.finalized_matches}.",
        f"- **Fecha más reciente (finalizado):** {src.latest_date}.",
        f"- **¿CSV derivado desactualizado vs feed?:** "
        f"{'sí' if src.staleness.get('csv_is_stale_vs_feed') else 'no'} "
        f"(feed={src.staleness.get('feed_finalized')}, csv={src.staleness.get('csv_finalized')}).",
        "",
        "## Auditoría de valores de status",
        "", "| status | count |", "|---|---|",
    ]
    for k in STATUS_BUCKETS:
        L.append(f"| {k} | {buckets[k]} |")
    if other:
        L.append("")
        L.append("Valores 'other' encontrados: " + ", ".join(f"`{k}`={v}" for k, v in other.items()))
    else:
        L.append("")
        L.append("_No se encontraron valores de status fuera de los esperados._")
    L.append("_Nota: 'ft' proviene de `status_detail`; el resto de `status_state`._")

    L += ["", "## Partidos finalizados (con marcador)", ""]
    if recs:
        L.append("| fecha | partido | marcador |")
        L.append("|---|---|---|")
        for r in recs:
            L.append(f"| {r.get('date','n/d')} | {r['title']} | {r['actual_score']} |")
    else:
        L.append("_No hay partidos finalizados en la fuente actual._")

    L += ["", "## Partidos excluidos y razón", "",
          f"Excluidos: **{len(excluded)}** (no tienen marcador real → no finalizados)."]
    if excluded:
        L.append("")
        L.append("| partido | status_state | razón |")
        L.append("|---|---|---|")
        for f in excluded[:200]:
            L.append(f"| {title_of(f)} | {f.get('status_state')} | sin actual_score (no jugado/sin resultado) |")

    if src.finalized_matches <= 3:
        L += ["", "## Aviso de actualización", "",
              f"- **La fuente local solo contiene {src.finalized_matches} finalizado(s).**",
              "- **Para actualizar más partidos hay que actualizar `fixtures_live_2026.json`** "
              "(p. ej. re-ejecutando `sync_live_data_2026.py`); este módulo no inventa resultados.",
              "- No se fabricaron marcadores: cada finalizado corresponde a un `actual_score` real del feed."]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(L)
    out_path.write_text(text, encoding="utf-8")
    return text


def generate_reports() -> None:
    write_source_consistency()
    write_data_inventory()


if __name__ == "__main__":
    generate_reports()
    print(f"Reportes generados:\n - {DATA_INVENTORY_MD}\n - {SOURCE_CONSISTENCY_CSV}")
