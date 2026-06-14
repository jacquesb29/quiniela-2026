"""Tests F0.4b: auditoría y re-derivación de Elo prepartido sin leakage."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.benchmarks import write_csv_rows  # noqa: E402
from worldcup2026.elo_rederive import (  # noqa: E402
    build_elo_comparison_rows,
    elo_audit_summary,
    rederive_walk_forward_elo,
)

VALIDATION_STATUS_JSON = ROOT / "outputs" / "validation_status.json"
REDERIVED_ELO_CSV = ROOT / "outputs" / "walk_forward" / "rederived_elo_matches.csv"


def _m(date, a, b, ga, gb, tournament="FIFA World Cup"):
    return {"date": date, "home_team": a, "away_team": b,
            "home_score": str(ga), "away_score": str(gb), "tournament": tournament}


def _mid(date, a, b):
    return f"{date.replace('-', '')}_{a}_vs_{b}".replace(" ", "_")


class TestRederiveElo(unittest.TestCase):
    def test_new_team_gets_initial_elo(self):
        raw = [_m("1990-06-01", "Alpha", "Beta", 3, 0)]
        re = rederive_walk_forward_elo(raw, initial_elo=1500.0)
        elo_a, elo_b = re[_mid("1990-06-01", "Alpha", "Beta")]
        self.assertEqual(elo_a, 1500.0)
        self.assertEqual(elo_b, 1500.0)

    def test_elo_updates_after_match_not_before(self):
        raw = [
            _m("1990-06-01", "Alpha", "Beta", 3, 0),   # Alpha gana
            _m("1990-06-05", "Alpha", "Gamma", 1, 1),  # luego Alpha juega de nuevo
        ]
        re = rederive_walk_forward_elo(raw, initial_elo=1500.0, k_factor=24.0)
        # En su PRIMER partido el pre-Elo es el inicial (update solo después).
        self.assertEqual(re[_mid("1990-06-01", "Alpha", "Beta")][0], 1500.0)
        # En el segundo, el pre-Elo de Alpha ya subió por haber ganado el primero.
        self.assertGreater(re[_mid("1990-06-05", "Alpha", "Gamma")][0], 1500.0)
        # Gamma es nueva -> 1500.
        self.assertEqual(re[_mid("1990-06-05", "Alpha", "Gamma")][1], 1500.0)

    def test_rederived_elo_uses_only_past_matches(self):
        base = [
            _m("1990-06-01", "Alpha", "Beta", 2, 1),
            _m("1990-06-05", "Alpha", "Gamma", 0, 0),
        ]
        flipped = [
            _m("1990-06-01", "Alpha", "Beta", 2, 1),
            _m("1990-06-05", "Alpha", "Gamma", 5, 0),  # cambia un partido FUTURO
        ]
        re_base = rederive_walk_forward_elo(base, initial_elo=1500.0)
        re_flip = rederive_walk_forward_elo(flipped, initial_elo=1500.0)
        # El pre-Elo del PRIMER partido no puede depender de un resultado posterior.
        self.assertEqual(
            re_base[_mid("1990-06-01", "Alpha", "Beta")],
            re_flip[_mid("1990-06-01", "Alpha", "Beta")],
        )

    def test_original_vs_rederived_elo_report_exists(self):
        original_rows = [
            {"match_id": _mid("1990-06-01", "Alpha", "Beta"), "date": "1990-06-01",
             "team_a": "Alpha", "team_b": "Beta", "elo_a_pre": "1500.000", "elo_b_pre": "1500.000"},
        ]
        rederived = {_mid("1990-06-01", "Alpha", "Beta"): (1500.0, 1500.0)}
        comparison = build_elo_comparison_rows(original_rows, rederived)
        required = {
            "elo_a_pre_original", "elo_b_pre_original", "elo_a_pre_rederived",
            "elo_b_pre_rederived", "elo_delta_a", "elo_delta_b", "elo_source_status",
        }
        self.assertTrue(required.issubset(set(comparison[0].keys())))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rederived_elo_matches.csv"
            write_csv_rows(path, comparison)
            with path.open(encoding="utf-8") as handle:
                cols = set(next(csv.reader(handle)))
            self.assertTrue(required.issubset(cols))
        # Si el artefacto real existe, también debe tener las columnas requeridas.
        if REDERIVED_ELO_CSV.exists():
            with REDERIVED_ELO_CSV.open(encoding="utf-8") as handle:
                real_cols = set(next(csv.reader(handle)))
            self.assertTrue(required.issubset(real_cols))

    def test_validation_status_leakage_flag_depends_on_elo_audit(self):
        # Auditoría limpia (deltas ~0) + code audit True -> leakage_warning False.
        clean_rows = [
            {"elo_a_pre_original": 1500.0 + i, "elo_b_pre_original": 1400.0 + i,
             "elo_a_pre_rederived": 1500.0 + i, "elo_b_pre_rederived": 1400.0 + i,
             "elo_delta_a": 0.0, "elo_delta_b": 0.0, "elo_source_status": "comparado"}
            for i in range(50)
        ]
        clean = elo_audit_summary(clean_rows, code_audit_walk_forward=True)
        self.assertFalse(clean["leakage_warning"])
        # Auditoría con divergencia grande -> leakage_warning True.
        dirty_rows = [
            {"elo_a_pre_original": 1500.0 + i, "elo_b_pre_original": 1400.0 + i,
             "elo_a_pre_rederived": 1500.0 + i + (i % 7) * 40.0,
             "elo_b_pre_rederived": 1400.0 - (i % 5) * 50.0,
             "elo_delta_a": -(i % 7) * 40.0, "elo_delta_b": (i % 5) * 50.0,
             "elo_source_status": "comparado"}
            for i in range(50)
        ]
        dirty = elo_audit_summary(dirty_rows, code_audit_walk_forward=True)
        self.assertTrue(dirty["leakage_warning"])
        # Aunque la re-derivación coincida, si el code audit falla -> sigue True.
        no_code = elo_audit_summary(clean_rows, code_audit_walk_forward=False)
        self.assertTrue(no_code["leakage_warning"])

        # Si el artefacto real existe, el flag del verdict debe derivarse de la auditoría.
        if VALIDATION_STATUS_JSON.exists():
            payload = json.loads(VALIDATION_STATUS_JSON.read_text(encoding="utf-8"))
            if "elo_leakage_audit" in payload and "elo_backtest_compare" in payload:
                expected = bool(
                    payload["elo_leakage_audit"]["leakage_warning"]
                    or not payload["elo_backtest_compare"]["backtest_stable"]
                )
                self.assertEqual(payload["verdict"]["leakage_warning"], expected)


if __name__ == "__main__":
    unittest.main()
