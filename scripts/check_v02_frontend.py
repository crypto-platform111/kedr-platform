"""Bounded current-release frontend checks; leaves 0.1 evidence unchanged."""
from pathlib import Path
from runtime_paths import node_directory
from datetime import datetime, timezone
import json
import os
import subprocess

root = Path(__file__).resolve().parents[1]
node_root = node_directory(root)
env = {**os.environ, "PATH": str(node_root) + os.pathsep + os.environ.get("PATH", "")}
output = root / "verification/v02"
output.mkdir(parents=True, exist_ok=True)
commands = {
    "typecheck": ["node_modules/typescript/bin/tsc", "--noEmit"],
    "lint": ["node_modules/eslint/bin/eslint.js", "src"],
    "build": ["node_modules/vite/bin/vite.js", "build"],
}
results = {}
for name, command in commands.items():
    result = subprocess.run([str(node_root / "node.exe"), *command], cwd=root / "frontend",
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    (output / f"frontend-{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    results[name] = {"exit_code": result.returncode, "log": f"frontend-{name}.log"}
    print(name, result.returncode, flush=True)
report = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": results,
          "all_passed": all(r["exit_code"] == 0 for r in results.values())}
(output / "frontend-checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
raise SystemExit(0 if report["all_passed"] else 1)
