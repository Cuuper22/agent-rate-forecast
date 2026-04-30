import json
import tempfile
import unittest
from pathlib import Path

from src.codex_rate_forecast import build_forecast, load_events_from_paths, render_png


def write_session(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class ForecastTests(unittest.TestCase):
    def test_extracts_documented_used_percent_windows_from_session_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_session(
                root / "sessions" / "2026" / "04" / "rollout.jsonl",
                [
                    {
                        "timestamp": "2026-04-29T20:00:00Z",
                        "type": "event_msg",
                        "payload": {"type": "token_count"},
                        "rate_limits": {
                            "primary": {
                                "used_percent": 10.0,
                                "window_minutes": 300,
                                "resets_at": 1777518000,
                            },
                            "secondary": {
                                "used_percent": 30.0,
                                "window_minutes": 10080,
                                "resets_at": 1778112000,
                            },
                        },
                    }
                ],
            )

            events = load_events_from_paths([root])

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].window_label, "5h")
        self.assertEqual(events[0].used_percent, 10.0)
        self.assertEqual(events[1].window_label, "weekly")
        self.assertEqual(events[1].reset_epoch, 1778112000)

    def test_extracts_generic_rate_limit_bucket_names_from_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_session(
                root / "agent.jsonl",
                [
                    {
                        "timestamp": "2026-04-29T20:00:00Z",
                        "rate_limits": {
                            "short": {
                                "used_ratio": 0.5,
                                "window_minutes": 60,
                                "resets_at": 1777503600,
                            }
                        },
                    }
                ],
            )

            events = load_events_from_paths([root])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].window_label, "60m")
        self.assertEqual(events[0].used_percent, 50.0)

    def test_forecast_does_not_invent_hit_time_when_slope_is_flat(self):
        forecast = build_forecast(
            [
                {
                    "observed_epoch": 1777500000,
                    "used_percent": 25.0,
                    "window_minutes": 300,
                    "reset_epoch": 1777518000,
                    "window_label": "5h",
                    "source": "fixture",
                },
                {
                    "observed_epoch": 1777500600,
                    "used_percent": 25.0,
                    "window_minutes": 300,
                    "reset_epoch": 1777518000,
                    "window_label": "5h",
                    "source": "fixture",
                },
            ],
            now_epoch=1777500900,
        )

        self.assertIsNone(forecast["windows"][0]["hit_epoch"])
        self.assertIn("flat", " ".join(forecast["windows"][0]["warnings"]).lower())

    def test_forecast_uses_observed_server_reset_not_local_guess(self):
        forecast = build_forecast(
            [
                {
                    "observed_epoch": 1777500000,
                    "used_percent": 50.0,
                    "window_minutes": 300,
                    "reset_epoch": 1777600000,
                    "window_label": "5h",
                    "source": "fixture",
                }
            ],
            now_epoch=1777500900,
        )

        self.assertEqual(forecast["windows"][0]["reset_epoch"], 1777600000)
        self.assertNotEqual(forecast["windows"][0]["reset_epoch"], 1777500000 + 300 * 60)

    def test_render_png_writes_real_png_image(self):
        forecast = build_forecast(
            [
                {
                    "observed_epoch": 1777500000,
                    "used_percent": 20.0,
                    "window_minutes": 300,
                    "reset_epoch": 1777518000,
                    "window_label": "5h",
                    "source": "fixture",
                },
                {
                    "observed_epoch": 1777500600,
                    "used_percent": 25.0,
                    "window_minutes": 300,
                    "reset_epoch": 1777518000,
                    "window_label": "5h",
                    "source": "fixture",
                },
            ],
            now_epoch=1777500900,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "forecast.png"
            render_png(forecast, output)
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
