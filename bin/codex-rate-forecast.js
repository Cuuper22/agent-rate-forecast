#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const { join } = require("node:path");

const script = join(__dirname, "..", "src", "codex_rate_forecast.py");
const candidates = process.platform === "win32" ? ["py", "python"] : ["python3", "python"];

for (const exe of candidates) {
  const args = exe === "py" ? ["-3", script, ...process.argv.slice(2)] : [script, ...process.argv.slice(2)];
  const result = spawnSync(exe, args, { stdio: "inherit" });
  if (result.error && result.error.code === "ENOENT") continue;
  process.exit(result.status ?? 1);
}

console.error("agent-rate-forecast requires Python 3 on PATH.");
process.exit(1);
