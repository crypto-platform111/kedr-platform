"""Run the locked frontend toolchain and retain machine-readable exit status."""
import json
import os
from pathlib import Path
from runtime_paths import node_directory
import subprocess
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
node_root = node_directory(root)
node = str(node_root / 'node.exe')
cwd = root / 'frontend'
env = {**os.environ, 'PATH': str(node_root) + os.pathsep + os.environ.get('PATH', '')}
commands = {
    'typecheck': [node, 'node_modules/typescript/bin/tsc', '--noEmit'],
    'lint': [node, 'node_modules/eslint/bin/eslint.js', 'src'],
    'build': [node, 'node_modules/vite/bin/vite.js', 'build'],
}
results = {}
for name, command in commands.items():
    completed = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    (root / f'verification/frontend-{name}.log').write_text(completed.stdout, encoding='utf-8')
    results[name] = {'exit_code': completed.returncode, 'log': f'frontend-{name}.log'}
    print(name, completed.returncode, flush=True)
report = {'completed_at': datetime.now(timezone.utc).isoformat(), 'checks': results,
          'all_passed': all(item['exit_code'] == 0 for item in results.values())}
(root / 'verification/frontend-checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
raise SystemExit(0 if report['all_passed'] else 1)
