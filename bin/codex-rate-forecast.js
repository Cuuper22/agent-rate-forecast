#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const { join } = require("node:path");

const script = join(__dirname, "..", "src", "codex_rate_forecast.py");
const candidates = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];
const wantsPng = !process.argv.some((arg, index, args) => {
  const value = arg === "--output" ? args[index + 1] : arg.startsWith("--output=") ? arg.slice(9) : "";
  return value.toLowerCase().endsWith(".svg");
});

function checkPython(exe) {
  const args = exe === "py"
    ? ["-3", "-c", wantsPng ? "import PIL" : "pass"]
    : ["-c", wantsPng ? "import PIL" : "pass"];
  return spawnSync(exe, args, { stdio: "ignore" }).status === 0;
}

for (const exe of candidates) {
  if (!checkPython(exe)) continue;
  const args = exe === "py" ? ["-3", script, ...process.argv.slice(2)] : [script, ...process.argv.slice(2)];
  const result = spawnSync(exe, args, { stdio: "inherit" });
  if (result.error && result.error.code === "ENOENT") continue;
  process.exit(result.status ?? 1);
}

console.error(wantsPng
  ? "agent-rate-forecast PNG output requires Python 3 with Pillow. Install with: python -m pip install pillow"
  : "agent-rate-forecast requires Python 3 on PATH.");
process.exit(1);
