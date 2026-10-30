"""Locate a developer-installed Node runtime, retaining the old local fallback."""
from pathlib import Path
import shutil


def node_directory(root: Path) -> Path:
    installed = shutil.which("node")
    if installed:
        return Path(installed).resolve().parent
    pointer = root / "tools/node-path.txt"
    if pointer.is_file():
        candidate = Path(pointer.read_text(encoding="utf-8-sig").strip())
        if (candidate / "node.exe").is_file() or (candidate / "node").is_file():
            return candidate
    raise RuntimeError("Install Node.js 24 and put node/npm on PATH. Portable runtimes are not included in Git.")
