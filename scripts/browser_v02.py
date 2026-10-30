"""Run real Edge browser workflows against the local platform only."""
from pathlib import Path
from runtime_paths import node_directory
import os
import subprocess

root = Path(__file__).resolve().parents[1]
(root / "verification/v02").mkdir(parents=True, exist_ok=True)
node_root = node_directory(root)
env = {**os.environ, "PATH": str(node_root) + os.pathsep + os.environ.get("PATH", "")}
result = subprocess.run([str(node_root / "node.exe"), "node_modules/@playwright/test/cli.js", "test"],
                        cwd=root / "frontend", env=env, capture_output=True, text=True,
                        encoding="utf-8", timeout=900)
(root / "verification/v02/e2e.log").write_text(result.stdout + result.stderr, encoding="utf-8")
print(result.stdout, flush=True)
print(result.stderr, flush=True)
raise SystemExit(result.returncode)
