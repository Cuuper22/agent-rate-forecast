from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WINDOW_LABELS = {
    300: "5h",
    10080: "weekly",
}


@dataclass(frozen=True)
class RateEvent:
    observed_epoch: float
    used_percent: float
    window_minutes: int
    reset_epoch: float
    window_label: str
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed_epoch": self.observed_epoch,
            "used_percent": self.used_percent,
            "window_minutes": self.window_minutes,
            "reset_epoch": self.reset_epoch,
            "window_label": self.window_label,
            "source": self.source,
        }


def parse_time(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def clamp_percent(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    if 0.0 <= value <= 100.0:
        return value
    return None


def clamp_ratio(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    if 0.0 <= value <= 1.0:
        return value * 100.0
    return None


def iter_jsonl_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    sessions = path / "sessions"
    roots = [sessions] if sessions.exists() else [path]
    for root in roots:
        yield from root.rglob("*.jsonl")


def extract_rate_events(row: dict[str, Any], source: str) -> list[RateEvent]:
    observed = parse_time(row.get("timestamp")) or parse_time(row.get("ts")) or time.time()
    limits = row.get("rate_limits")
    if not isinstance(limits, dict):
        payload = row.get("payload")
        if isinstance(payload, dict):
            limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return []

    events: list[RateEvent] = []
    for key, bucket in limits.items():
        bucket = limits.get(key)
        if not isinstance(bucket, dict):
            continue
        used = clamp_percent(bucket.get("used_percent"))
        if used is None:
            used = clamp_ratio(bucket.get("used_ratio"))
        if used is None:
            remaining = clamp_percent(bucket.get("remaining_percent"))
            used = None if remaining is None else 100.0 - remaining
        if used is None:
            remaining = clamp_ratio(bucket.get("remaining_ratio"))
            used = None if remaining is None else 100.0 - remaining
        window_minutes = bucket.get("window_minutes")
        reset_epoch = parse_time(bucket.get("resets_at"))
        if used is None or not isinstance(window_minutes, int) or reset_epoch is None:
            continue
        events.append(
            RateEvent(
                observed_epoch=observed,
                used_percent=used,
                window_minutes=window_minutes,
                reset_epoch=reset_epoch,
                window_label=WINDOW_LABELS.get(window_minutes, f"{window_minutes}m"),
                source=source,
            )
        )
    return events


def load_events_from_paths(paths: list[Path]) -> list[RateEvent]:
    events: list[RateEvent] = []
    for path in paths:
        for jsonl_path in iter_jsonl_files(path.expanduser()):
            try:
                with jsonl_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(row, dict):
                            events.extend(extract_rate_events(row, str(jsonl_path)))
            except OSError:
                continue
    events.sort(key=lambda event: (event.window_minutes, event.observed_epoch))
    return events


def default_log_paths() -> list[Path]:
    paths: list[Path] = []
    home = os.environ.get("CODEX_HOME")
    if home:
        paths.append(Path(home))
    paths.append(Path.home() / ".codex")
    paths.append(Path.home() / ".claude")
    return paths


def linear_hit_epoch(points: list[RateEvent], now_epoch: float) -> tuple[float | None, list[str], float]:
    warnings: list[str] = []
    if len(points) < 2:
        warnings.append("Need at least two observed samples for a slope; hit time is unknown.")
        return None, warnings, 0.0

    recent = points[-min(24, len(points)) :]
    xs = [event.observed_epoch for event in recent]
    ys = [event.used_percent for event in recent]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom <= 0:
        warnings.append("Observed samples have no time spread; hit time is unknown.")
        return None, warnings, 0.0
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    if slope <= 1e-9:
        warnings.append("Recent usage slope is flat or decreasing; hit time is unknown.")
        return None, warnings, slope
    last = recent[-1]
    seconds_to_full = (100.0 - last.used_percent) / slope
    if seconds_to_full < 0:
        return now_epoch, warnings, slope
    return last.observed_epoch + seconds_to_full, warnings, slope


def sample_points(points: list[RateEvent], limit: int = 200) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return [point.as_dict() for point in points]
    step = (len(points) - 1) / (limit - 1)
    sampled = [points[round(index * step)].as_dict() for index in range(limit)]
    return sampled


def build_forecast(raw_events: list[RateEvent | dict[str, Any]], now_epoch: float | None = None) -> dict[str, Any]:
    now_epoch = time.time() if now_epoch is None else now_epoch
    events = [event if isinstance(event, RateEvent) else RateEvent(**event) for event in raw_events]
    windows: list[dict[str, Any]] = []
    for label in sorted({event.window_label for event in events}, key=lambda item: (item != "5h", item)):
        points = [event for event in events if event.window_label == label]
        latest = points[-1]
        hit_epoch, warnings, slope = linear_hit_epoch(points, now_epoch)
        if hit_epoch is not None and hit_epoch > latest.reset_epoch:
            warnings.append("Projected hit falls after server-reported reset; current pace does not exhaust this window.")
        windows.append(
            {
                "label": label,
                "window_minutes": latest.window_minutes,
                "observations": len(points),
                "used_percent": round(latest.used_percent, 3),
                "remaining_percent": round(100.0 - latest.used_percent, 3),
                "reset_epoch": latest.reset_epoch,
                "hit_epoch": hit_epoch,
                "slope_percent_per_hour": round(slope * 3600.0, 5),
                "warnings": warnings,
                "source": latest.source,
                "sampled_points": sample_points(points),
            }
        )
    return {
        "generated_epoch": now_epoch,
        "windows": windows,
        "note": "Estimate from local Codex logs. Server-side enforcement, bursty use, plan changes, and sparse logging can move the real result.",
    }


def fmt_epoch(epoch: float | None) -> str:
    if epoch is None or not math.isfinite(epoch):
        return "unknown"
    return datetime.fromtimestamp(epoch, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def render_svg(forecast: dict[str, Any]) -> str:
    width, height = 1100, 660
    panel_h = 250
    rows = []
    for idx, window in enumerate(forecast["windows"]):
        y0 = 56 + idx * (panel_h + 26)
        used = max(0.0, min(100.0, float(window["used_percent"])))
        remaining = 100.0 - used
        bar_w = 760
        fill_w = bar_w * used / 100.0
        rows.append(
            f"""
  <g transform="translate(52 {y0})">
    <rect width="996" height="{panel_h}" rx="14" fill="#fbfbfd" stroke="#dedee7"/>
    <text x="28" y="46" font-size="20" font-weight="700" fill="#111827">{window['label']} window</text>
    <text x="28" y="92" font-size="44" font-weight="800" fill="#111827">{remaining:.1f}%</text>
    <text x="184" y="92" font-size="18" fill="#6b7280">remaining</text>
    <text x="760" y="55" font-size="16" fill="#374151">resets {fmt_epoch(window['reset_epoch'])}</text>
    <rect x="28" y="122" width="{bar_w}" height="14" rx="7" fill="#e5e7eb"/>
    <rect x="28" y="122" width="{fill_w:.2f}" height="14" rx="7" fill="#22c55e"/>
    <text x="28" y="166" font-size="15" fill="#374151">{used:.1f}% used</text>
    <text x="158" y="166" font-size="15" fill="#6b7280">{remaining:.1f}% remaining</text>
    <text x="28" y="207" font-size="18" font-weight="700" fill="#7c3aed">Predicted limit hit: {fmt_epoch(window['hit_epoch'])}</text>
    <text x="28" y="232" font-size="14" fill="#6b7280">Slope {window['slope_percent_per_hour']}%/hour from {window['observations']} observations. {window['warnings'][0] if window['warnings'] else 'Linear projection only.'}</text>
  </g>"""
        )
    body = "\n".join(rows)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f4f4f7"/>
  <text x="52" y="36" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="24" font-weight="800" fill="#111827">Agent Rate Forecast</text>
  <g font-family="Inter, Segoe UI, Arial, sans-serif">{body}
  </g>
  <text x="52" y="{height - 28}" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13" fill="#6b7280">{forecast['note']}</text>
</svg>
"""


def print_summary(forecast: dict[str, Any]) -> None:
    print("Agent rate forecast")
    print(f"Generated: {fmt_epoch(forecast['generated_epoch'])}")
    for window in forecast["windows"]:
        print()
        print(f"{window['label']}: {window['used_percent']}% used, {window['remaining_percent']}% remaining")
        print(f"  reset: {fmt_epoch(window['reset_epoch'])}")
        print(f"  projected hit: {fmt_epoch(window['hit_epoch'])}")
        print(f"  slope: {window['slope_percent_per_hour']}%/hour from {window['observations']} observations")
        for warning in window["warnings"]:
            print(f"  warning: {warning}")
    print()
    print(forecast["note"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forecast coding-agent rate limit usage from local logs.")
    parser.add_argument("--path", action="append", type=Path, default=[], help="Log file or directory. May be repeated.")
    parser.add_argument("--codex-home", type=Path, default=None, help="Backward-compatible alias for --path.")
    parser.add_argument("--output", type=Path, default=Path("agent-rate-forecast.svg"))
    parser.add_argument("--json", type=Path, default=None, help="Optional path for machine-readable forecast JSON.")
    args = parser.parse_args(argv)

    paths = list(args.path)
    if args.codex_home:
        paths.append(args.codex_home)
    if not paths:
        paths = [path for path in default_log_paths() if path.exists()]
    events = load_events_from_paths(paths)
    if not events:
        searched = ", ".join(str(path) for path in paths) or "(no existing default paths)"
        print(f"No rate-limit events found under {searched}", file=sys.stderr)
        return 2
    forecast = build_forecast(events)
    args.output.write_text(render_svg(forecast), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(forecast, indent=2), encoding="utf-8")
    print_summary(forecast)
    print(f"\nPlot: {args.output.resolve()}")
    if args.json:
        print(f"JSON: {args.json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
