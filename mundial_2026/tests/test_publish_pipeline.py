from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


class PublishPipelineTest(unittest.TestCase):
    def test_build_pages_site_creates_aligned_site_payload(self):
        script_path = PACKAGE_ROOT / "build_pages_site.sh"

        with tempfile.TemporaryDirectory() as tmpdir:
            publish_root = Path(tmpdir) / "mundial_2026"
            publish_root.mkdir(parents=True, exist_ok=True)

            (publish_root / "dashboard_actual_2026.html").write_text("<html><body>dashboard</body></html>")
            (publish_root / "reporte_actual_2026.md").write_text("# Reporte\n")
            (publish_root / "llave_actual_2026.md").write_text("# Llave\n")
            (publish_root / "llave_actual_2026.json").write_text(json.dumps({"iterations": 100000}))
            (publish_root / "fixtures_live_2026.json").write_text(
                json.dumps(
                    [
                        {
                            "source": "espn_scoreboard",
                            "live_feed_provider": "api_football",
                        }
                    ]
                )
            )
            (publish_root / "teams_2026.json").write_text(
                json.dumps({"meta": {"fifa_rankings_as_of": "2026-05-10"}})
            )
            (publish_root / "historical_features_1950.json").write_text(
                json.dumps(
                    {
                        "meta": {
                            "from_date": "1950-01-01",
                            "official_matches_since_start": 29562,
                            "minimum_official_matches_required": 25000,
                            "official_match_definition": "Partidos internacionales oficiales.",
                        }
                    }
                )
            )

            env = dict(os.environ)
            env["WORLDCUP_PUBLISH_ROOT"] = str(publish_root)
            completed = subprocess.run(
                ["bash", str(script_path)],
                cwd=PACKAGE_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0)

            site_dir = publish_root / "site"
            latest_path = site_dir / "latest.json"
            self.assertTrue(latest_path.exists())
            self.assertEqual(
                (site_dir / "index.html").read_text(),
                (publish_root / "dashboard_actual_2026.html").read_text(),
            )

            latest = json.loads(latest_path.read_text())
            self.assertEqual(latest["refresh_interval_minutes"], 5)
            self.assertEqual(latest["live_refresh_interval_minutes"], 5)
            self.assertEqual(latest["deep_bracket_refresh_interval_minutes"], 480)
            self.assertEqual(latest["deep_bracket_minimum_iterations"], 100000)
            self.assertEqual(latest["monte_carlo_iterations"], 100000)
            self.assertEqual(latest["delivery"], "github_actions_pages")
            self.assertTrue(latest["in_play_enabled"])
            self.assertEqual(latest["live_feed_stack"], ["espn_scoreboard"])
            self.assertEqual(latest["live_feed_providers"], ["api_football"])
            self.assertEqual(latest["official_fifa_rankings_as_of"], "2026-05-10")
            self.assertEqual(latest["historical_base"]["from_date"], "1950-01-01")
            self.assertEqual(latest["historical_base"]["official_matches"], 29562)
            self.assertEqual(latest["historical_base"]["minimum_official_matches_required"], 25000)
            robustness = latest["predictive_robustness_gate"]
            self.assertEqual(robustness["status"], "pretorneo_sin_muestra_2026")
            self.assertFalse(robustness["calibration_2026_active"])
            self.assertTrue(robustness["deep_live_feed_active"])
            self.assertTrue(robustness["proxy_inputs_blocked"])
            self.assertIn("primer partido finalizado", robustness["brier_2026_policy"])
            self.assertIn("90-95", robustness["exact_score_single_pick_policy"])
            self.assertEqual(latest["files"]["dashboard"], "dashboard_actual_2026.html")
            self.assertEqual(latest["files"]["historical_features"], "historical_features_1950.json")
            self.assertTrue((site_dir / "historical_features_1950.json").exists())
            datetime.fromisoformat(latest["updated_at_utc"])


if __name__ == "__main__":
    unittest.main()
