# agent-rate-forecast

A tiny skill plus npm CLI that reads local coding-agent logs, extracts server-reported rate-limit snapshots, and renders a compact forecast plot.

It prefers documented snapshot fields when they are present:

- `rate_limits.<bucket>.used_percent`
- `rate_limits.<bucket>.used_ratio`
- `rate_limits.<bucket>.remaining_percent`
- `rate_limits.<bucket>.remaining_ratio`
- `rate_limits.<bucket>.window_minutes`
- `rate_limits.<bucket>.resets_at`

The script does not treat unknown floats as truth. If there are too few samples or the slope is flat, it says the hit time is unknown instead of inventing a clean answer.

## Use

```bash
npx agent-rate-forecast --output agent-rate-forecast.svg --json agent-rate-forecast.json
```

For a nonstandard log location:

```bash
npx agent-rate-forecast --path /path/to/logs
```

Codex is supported out of the box via `CODEX_HOME` or `~/.codex`. Other agents work when their JSONL logs contain a `rate_limits` object with the fields above, or when you point `--path` at exported JSONL in that shape. Percent fields are literal percentages; ratio fields are explicit ratios.

## Skill

Install or copy `skills/rate-limit-forecast/SKILL.md` into a skills directory. The skill stays intentionally small: run the CLI, report the estimate, include warnings.
