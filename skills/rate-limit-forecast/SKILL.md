---
name: rate-limit-forecast
description: Use when a user asks for coding-agent rate limits, quota remaining, reset timing, local log evidence, burn-rate projection, or a plotted usage forecast.
---

# Rate Limit Forecast

Run:

```bash
npx agent-rate-forecast --output agent-rate-forecast.png --json agent-rate-forecast.json
```

Use `--path <log-or-directory>` for non-default logs. The tool supports JSONL snapshots with `rate_limits.*.used_percent`, `used_ratio`, `remaining_percent`, `remaining_ratio`, `window_minutes`, and `resets_at`; Codex logs are found from `CODEX_HOME` or `~/.codex`.

Report the observed used/remaining percent, reset time, projected hit time, generated PNG/JSON paths, and any warnings. Show the PNG inline when the interface supports local images. If the tool says `unknown`, keep it unknown. Call it an estimate from local logs because sparse logging, bursty usage, plan changes, and server enforcement can differ.
