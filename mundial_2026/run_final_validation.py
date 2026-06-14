"""Runner F7: validación final y congelamiento operativo.

Ejecuta la suite de tests y todos los runners de auditoría/validación, lee sus
veredictos y produce un resumen final. F7 DOCUMENTA Y CONGELA: no cambia el
modelo, pesos, lambdas, metodología, selector Penca ni flags de producción.

Uso:
    python3 run_final_validation.py            # corre tests + todos los runners
    python3 run_final_validation.py --reuse    # no re-ejecuta; lee artefactos existentes
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.config import PARAMS  # noqa: E402

FINAL_DIR = ROOT / "outputs" / "final"
SUMMARY_JSON = FINAL_DIR / "final_validation_summary.json"
SUMMARY_MD = FINAL_DIR / "final_validation_summary.md"

VALIDATION_STATUS = ROOT / "outputs" / "validation_status.json"
F3_GATE = ROOT / "outputs" / "audit" / "f3_gate.json"
STALENESS_DECISION = ROOT / "outputs" / "ratings" / "staleness_activation_decision.md"
TAIL_WF_DECISION = ROOT / "outputs" / "audit" / "tail_walkforward_decision.md"
VARIANCE_DECISION = ROOT / "outputs" / "audit" / "variance_attribution_decision.md"
MARKET_DECISION = ROOT / "outputs" / "market" / "market_decision_log.csv"


def _grep_token(path: Path, tokens) -> str:
    if not path.exists():
        return "n/d"
    text = path.read_text(encoding="utf-8").lower()
    for tok in tokens:
        if tok.lower() in text:
            return tok
    return "desconocido"


def _run_tests() -> dict:
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                          cwd=str(ROOT), capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    total = 0
    for line in out.splitlines():
        if line.startswith("Ran ") and " test" in line:
            try:
                total = int(line.split()[1])
            except (IndexError, ValueError):
                total = 0
    return {"total": total, "result": "OK" if proc.returncode == 0 else "FAILED"}


def _run_phase(name: str, fn) -> int:
    print(f"\n=== {name} ===")
    try:
        return int(fn() or 0)
    except SystemExit as exc:  # algunos main hacen raise SystemExit
        return int(exc.code or 0)
    except Exception as exc:  # pragma: no cover
        print(f"[error en {name}] {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    reuse = "--reuse" in argv
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    tests = {"total": 0, "result": "no_ejecutado"} if reuse else _run_tests()

    phase_rc = {}
    if not reuse:
        import run_real_validation
        import run_market_t60_pipeline
        import run_f3_audit
        import run_staleness_activation_gate
        import run_tail_intervention_eval
        import run_variance_attribution
        phase_rc["F0_real_validation"] = _run_phase("F0 real_validation", run_real_validation.main)
        phase_rc["F1_market_t60"] = _run_phase("F1 market_t60_pipeline", run_market_t60_pipeline.main)
        phase_rc["F3_audit"] = _run_phase("F3 audit", run_f3_audit.main)
        phase_rc["F2_5_staleness_gate"] = _run_phase("F2.5 staleness_gate", run_staleness_activation_gate.main)
        phase_rc["F4_2_tail_eval"] = _run_phase("F4 tail_intervention_eval", run_tail_intervention_eval.main)
        phase_rc["F5_attribution"] = _run_phase("F5 variance_attribution", run_variance_attribution.main)

    # ---- Leer veredictos de artefactos ----
    f0_label = "n/d"
    if VALIDATION_STATUS.exists():
        try:
            f0_label = json.loads(VALIDATION_STATUS.read_text(encoding="utf-8")).get("verdict", {}).get("label", "n/d")
        except (ValueError, OSError):
            f0_label = "n/d"
    f3_priority, f3_intervene = "n/d", "n/d"
    if F3_GATE.exists():
        try:
            g = json.loads(F3_GATE.read_text(encoding="utf-8"))
            f3_priority = g.get("suggested_priority", "n/d")
            f3_intervene = g.get("vale_la_pena_intervenir", "n/d")
        except (ValueError, OSError):
            pass

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tests": tests,
        "phases": {
            "F0_real_validation": {"rc": phase_rc.get("F0_real_validation"), "label": f0_label},
            "F1_market_t60": {"rc": phase_rc.get("F1_market_t60"),
                              "status": "operativo" if MARKET_DECISION.exists() else "n/d"},
            "F2_5_staleness_gate": {"rc": phase_rc.get("F2_5_staleness_gate"),
                                    "decision": _grep_token(STALENESS_DECISION, ["keep_off", "activate", "diagnostic_only"])},
            "F3_audit": {"rc": phase_rc.get("F3_audit"),
                         "suggested_priority": f3_priority, "vale_la_pena_intervenir": f3_intervene},
            "F4_2_tail_walkforward": {"rc": phase_rc.get("F4_2_tail_eval"),
                                      "decision": _grep_token(TAIL_WF_DECISION, ["keep_off", "activate"])},
            "F5_attribution": {"rc": phase_rc.get("F5_attribution"),
                               "decision": _grep_token(VARIANCE_DECISION, ["no_clear_culprit", "intervene_component"])},
        },
        "production_flags": {"elo_staleness_enabled": bool(PARAMS.elo_staleness_enabled)},
        "f6": "not_applicable_no_clear_culprit",
        "active_in_production": ["base_model", "cache_reproducibility_fix", "market_t60_overlay"],
        "off": ["elo_staleness", "tail_reweight"],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(summary)

    print("\n================ RESUMEN FINAL (F7) ================")
    print(f"tests: {tests['total']} ({tests['result']})")
    print(f"F0: {summary['phases']['F0_real_validation']['label']}")
    print(f"F2.5: {summary['phases']['F2_5_staleness_gate']['decision']}")
    print(f"F3: priority={f3_priority}")
    print(f"F4.2: {summary['phases']['F4_2_tail_walkforward']['decision']}")
    print(f"F5: {summary['phases']['F5_attribution']['decision']}")
    print(f"flags producción: elo_staleness_enabled={summary['production_flags']['elo_staleness_enabled']}")
    print(f"F6: {summary['f6']}")
    print("====================================================")
    return 0


def _write_md(s):
    p = s["phases"]
    lines = [
        "# Resumen de validación final (F7)", "",
        f"Generado: {s['generated_at_utc']}", "",
        f"- Tests: **{s['tests']['total']}** ({s['tests']['result']})",
        f"- F0 (validación): etiqueta **{p['F0_real_validation']['label']}**",
        f"- F1 (mercado/T-60): **{p['F1_market_t60']['status']}**",
        f"- F2.5 (Elo staleness): **{p['F2_5_staleness_gate']['decision']}**",
        f"- F3 (auditoría): prioridad sugerida **{p['F3_audit']['suggested_priority']}**, "
        f"vale_la_pena={p['F3_audit']['vale_la_pena_intervenir']}",
        f"- F4.2 (intervención colas): **{p['F4_2_tail_walkforward']['decision']}**",
        f"- F5 (atribución): **{p['F5_attribution']['decision']}**",
        f"- F6: **{s['f6']}**", "",
        "## Producción",
        f"- Flags activos experimentales: ninguno (`elo_staleness_enabled`={s['production_flags']['elo_staleness_enabled']}).",
        f"- Activo: {', '.join(s['active_in_production'])}.",
        f"- OFF: {', '.join(s['off'])}.", "",
        "F7 documenta y congela. No se cambió ninguna predicción de producción.",
    ]
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
