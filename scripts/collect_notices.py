"""Collect installed software notices without changing package files."""
from pathlib import Path
from runtime_paths import node_directory
import json

root = Path(__file__).resolve().parents[1]
(root / "verification/v02").mkdir(parents=True, exist_ok=True)
package_root = root / 'frontend'
lock = json.loads((package_root / 'package-lock.json').read_text())
chunks = ['KEDR local software dependency notices\nGenerated from the locked installed dependency tree.\n']
seen = set()
for relative, package in sorted(lock['packages'].items()):
    if not relative:
        continue
    folder = package_root / relative
    chunks.append(f"\n\n## {relative} {package.get('version', '')}\nDeclared license: {package.get('license', 'see package')}\n")
    for file in folder.iterdir() if folder.is_dir() else []:
        if file.is_file() and file.name.lower().startswith(('license', 'licence', 'notice', 'copying')):
            resolved = file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            assert file.stat().st_size < 1024 * 1024
            chunks.append(f'\n### {file.name}\n' + file.read_text(encoding='utf-8', errors='replace'))
node_root = node_directory(root)
if (node_root / 'LICENSE').is_file():
    chunks.append('\n\n## Portable Node runtime\n' + (node_root / 'LICENSE').read_text(encoding='utf-8'))
text = ''.join(chunks)
assert len(text.encode('utf-8')) < 16 * 1024 * 1024
(root / 'verification/third-party-notices.txt').write_text(text, encoding='utf-8')
print(f'{len(seen)} package notice files retained; {len(text.encode("utf-8"))} bytes.')
