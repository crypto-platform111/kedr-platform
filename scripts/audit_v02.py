"""Bounded advisory/license checks for this installation, no package installation."""
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from runtime_paths import node_directory
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

root = Path(__file__).resolve().parents[1]
out = root / "verification/v02"
out.mkdir(parents=True, exist_ok=True)
node_root = node_directory(root)
env = {**os.environ, "PATH": str(node_root) + os.pathsep + os.environ.get("PATH", "")}
packages = sorted([{"name": d.metadata["Name"], "version": d.version,
                    "license": d.metadata.get("License-Expression") or d.metadata.get("License")}
                   for d in metadata.distributions()], key=lambda r: r["name"].lower())
assert len(packages) <= 64
payload = json.dumps({"queries": [{"package": {"name": p["name"], "ecosystem": "PyPI"},
                                  "version": p["version"]} for p in packages]}).encode()
request = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=payload,
                                 headers={"Content-Type": "application/json", "User-Agent": "KEDR-local-audit/0.2"})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(4 * 1024 * 1024 + 1)
        assert len(body) <= 4 * 1024 * 1024
    decoded = json.loads(body)
    assert len(decoded["results"]) == len(packages)
    findings = [{"package": p["name"], "version": p["version"], "result": r}
                for p, r in zip(packages, decoded["results"]) if r.get("vulns") or r.get("next_page_token")]
    osv = {"status": "completed", "findings": findings, "response_sha256": hashlib.sha256(body).hexdigest()}
    (out / "python-osv.json").write_bytes(body)
except Exception as exc:
    osv = {"status": "unavailable", "reason": type(exc).__name__}
check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, timeout=60)
python_report = {"checked_at": datetime.now(timezone.utc).isoformat(), "packages": packages,
                 "pip_check_exit_code": check.returncode, "pip_check": check.stdout.strip(), "osv": osv,
                 "limitation": "Version advisory matching is not a security certification."}
(out / "python-dependencies.json").write_text(json.dumps(python_report, indent=2), encoding="utf-8")
print("Python audit", osv["status"], "pip check", check.returncode, flush=True)
npm = subprocess.run([str(node_root / "node.exe"), str(node_root / "node_modules/npm/bin/npm-cli.js"),
                      "audit", "--json", "--ignore-scripts", "--cache", str(root / ".cache/npm")],
                     cwd=root / "frontend", env=env, capture_output=True, text=True, encoding="utf-8", timeout=90)
(out / "npm-audit.json").write_text(npm.stdout, encoding="utf-8")
(out / "npm-audit.stderr.log").write_text(npm.stderr, encoding="utf-8")
lock = json.loads((root / "frontend/package-lock.json").read_text())
declared = [{"path": p, "version": v.get("version"), "license": v.get("license"), "integrity": v.get("integrity")}
            for p, v in lock["packages"].items() if p]
(out / "npm-dependencies.json").write_text(json.dumps(declared, indent=2), encoding="utf-8")
assert len(declared) <= 300
notices = []
for p in (root / "frontend/node_modules/echarts/LICENSE", root / "frontend/node_modules/echarts/NOTICE"):
    if p.exists():
        notices.append({"path": str(p.relative_to(root)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size})
assert len(notices) == 2
(out / "chart-license.json").write_text(json.dumps({"package": "echarts", "version": lock["packages"]["node_modules/echarts"]["version"],
            "license": "Apache-2.0", "notices": notices, "dependency_changes": "No packages added; application version only changed in lockfile."}, indent=2), encoding="utf-8")
print("npm audit exit", npm.returncode, "locked packages", len(declared), "chart notices", len(notices), flush=True)
raise SystemExit(0 if check.returncode == 0 and osv.get("status") == "completed" and not osv.get("findings") and npm.returncode == 0 else 1)
