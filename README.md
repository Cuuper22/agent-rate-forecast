# agent-rate-forecast

A tiny skill plus npm CLI that reads local coding-agent logs, extracts server-reported rate-limit snapshots, and renders a compact forecast plot.

## Why

I kept hitting coding-agent limits mid-run and wanted a boring answer to a practical question: "Am I about to run out, or can I keep going?" The trap is that local logs are messy. Some entries have explicit rate-limit snapshots. Some have unrelated floats. Some have too few samples to support a forecast.

This tool is intentionally conservative. It prefers documented `rate_limits` fields, fits a simple slope only when there is enough signal, and says "unknown" when the evidence is thin. A wrong clean answer is worse than a fuzzy honest one.

## What This Shows

- Treats local logs as evidence, not as an excuse to hallucinate quota math.
- Ships the same core as both an npm CLI and an agent skill.
- Keeps the forecast readable: a PNG for humans, JSON for automation, warnings when the estimate is weak.

It prefers documented snapshot fields when they are present:

- `rate_limits.<bucket>.used_percent`
- `rate_limits.<bucket>.used_ratio`
- `rate_limits.<bucket>.remaining_percent`
- `rate_limits.<bucket>.remaining_ratio`
- `rate_limits.<bucket>.window_minutes`
- `rate_limits.<bucket>.resets_at`

The script does not treat unknown floats as truth. If there are too few samples or the slope is flat, it says the hit time is unknown instead of inventing a clean answer.

## What To Inspect

- `src/codex_rate_forecast.py` for log discovery, snapshot extraction, slope fitting, and PNG rendering.
- `bin/codex-rate-forecast.js` for the npm wrapper that runs the Python implementation.
- `tests/test_forecast.py` for the edge cases around missing fields, ratios vs. percentages, and unknown hit times.
- `skills/rate-limit-forecast/SKILL.md` for how the CLI becomes an agent skill.

## Use

```bash
npx agent-rate-forecast --output agent-rate-forecast.png --json agent-rate-forecast.json
```

For a nonstandard log location:

```bash
npx agent-rate-forecast --path /path/to/logs
```

Codex is supported out of the box via `CODEX_HOME` or `~/.codex`. Other agents work when their JSONL logs contain a `rate_limits` object with the fields above, or when you point `--path` at exported JSONL in that shape. Percent fields are literal percentages; ratio fields are explicit ratios. PNG output requires Python Pillow.

## Skill

Install or copy `skills/rate-limit-forecast/SKILL.md` into a skills directory. The skill stays intentionally small: run the CLI, report the estimate, include warnings.
