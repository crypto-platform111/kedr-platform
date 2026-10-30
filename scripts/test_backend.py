"""Run isolated backend tests with the active Python interpreter, on any drive."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


project = Path(__file__).resolve().parents[1]
environment = dict(os.environ)
# Local-only installed sources are optional. No real .env or credential file is
# read here. An explicit environment value (including blank) always takes priority.
settings_path = project / "data" / "local-settings.json"
if "KEDR_LEGACY_ROOT" not in environment and settings_path.is_file():
    settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    if isinstance(settings.get("KEDR_LEGACY_ROOT"), str):
        environment["KEDR_LEGACY_ROOT"] = settings["KEDR_LEGACY_ROOT"]
with tempfile.TemporaryDirectory(prefix="kedr-backend-check-") as temporary:
    environment["KEDR_DATA_DIR"] = str(Path(temporary) / "app")
    command = [sys.executable, "-m", "pytest", "backend/tests", "-q", "--basetemp", str(Path(temporary) / "pytest")]
    result = subprocess.run(command, cwd=project, env=environment, capture_output=True, text=True, encoding="utf-8")
    output = project / "verification"
    output.mkdir(exist_ok=True)
    (output / "backend-tests.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    (output / "backend-tests-status.json").write_text(json.dumps({
        "command": command, "exit_code": result.returncode, "verified_at": datetime.now(timezone.utc).isoformat(),
        "database_isolated": True, "optional_historical_root_configured": bool(environment.get("KEDR_LEGACY_ROOT", "").strip()),
    }, indent=2), encoding="utf-8")
    print(result.stdout)
    print(result.stderr)
    sys.exit(result.returncode)
