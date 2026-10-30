"""Fail-closed source/index/history checks before sharing KEDR.

This is a reproducible local check, not a guarantee against every secret format.
Reports contain paths/rules only, never matching secret values.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git") or str(ROOT / "tools/share-tools/git/cmd/git.exe")
FORBIDDEN_PARTS = {"data", "backups", "exports", "verification", "tools", "node_modules", ".venv", "venv", ".tmp", ".cache", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build", "test-results", "playwright-report"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".zip", ".gz", ".npy", ".npz", ".parquet", ".pkl", ".pickle", ".joblib", ".exe", ".dll", ".log", ".pem", ".key", ".pfx", ".pdf", ".docx"}
PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{35,})\b"),
    "openai_key": re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "google_api_key": re.compile(rb"\bAIza[A-Za-z0-9_-]{30,}\b"),
    "slack_token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "jwt": re.compile(rb"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b"),
    "embedded_url_password": re.compile(rb"https?://[^\s/@:]+:[^\s/@]{5,}@"),
}


def git(*args, allow_unborn=False):
    result = subprocess.run([GIT, "-C", str(ROOT), *args], capture_output=True)
    if result.returncode and not allow_unborn:
        raise RuntimeError("Git inspection failed: " + " ".join(args[:2]))
    return result.stdout


def inspect_blob(path, payload, findings):
    parts = Path(path).parts
    if any(p.lower() in FORBIDDEN_PARTS for p in parts) or Path(path).suffix.lower() in FORBIDDEN_SUFFIXES:
        findings.append({"path": path, "rule": "forbidden_private_or_generated_path"})
    if Path(path).name.startswith(".env") and Path(path).name != ".env.example":
        findings.append({"path": path, "rule": "real_environment_file"})
    if len(payload) > 8 * 1024 * 1024:
        findings.append({"path": path, "rule": "file_exceeds_source_size_cap"})
    if payload.startswith(b"SQLite format 3\0") or b"\0" in payload:
        findings.append({"path": path, "rule": "unexpected_binary_or_database_payload"})
    for rule, pattern in PATTERNS.items():
        for match in pattern.finditer(payload):
            findings.append({"path": path, "rule": rule, "line": payload[:match.start()].count(b"\n") + 1})
    if Path(path).name == ".env.example":
        for line_number, line in enumerate(payload.decode("utf-8-sig").splitlines(), 1):
            if line.lstrip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if re.search(r"(?:KEY|TOKEN|PASSWORD|SECRET)$", name) and value.strip().strip("\"'") not in ("", "disabled", "CHANGE_ME"):
                findings.append({"path": path, "rule": "nonplaceholder_example_secret", "line": line_number})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--report", default="verification/github-upload/security-scan.json")
    args = parser.parse_args()
    findings, files = [], []
    if args.staged:
        for item in git("ls-files", "--stage", "-z").split(b"\0"):
            if not item:
                continue
            info, raw_path = item.split(b"\t", 1)
            mode, blob, stage = info.decode().split()
            path = raw_path.decode("utf-8")
            if mode not in ("100644", "100755") or stage != "0":
                findings.append({"path": path, "rule": "symlink_submodule_or_unmerged_index"})
            payload = git("cat-file", "blob", blob)
            inspect_blob(path, payload, findings)
            files.append({"path": path, "bytes": len(payload), "git_blob": blob, "sha256": hashlib.sha256(payload).hexdigest()})
    else:
        names = set(git("ls-files", "-z").split(b"\0") + git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"))
        for raw_path in sorted(names - {b""}):
            path = raw_path.decode("utf-8")
            file = ROOT / path
            if not file.resolve().is_relative_to(ROOT) or file.is_symlink() or file.is_junction():
                findings.append({"path": path, "rule": "outside_project_or_reparse_point"})
                continue
            payload = file.read_bytes()
            inspect_blob(path, payload, findings)
            files.append({"path": path, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    if sum(r["bytes"] for r in files) > 20 * 1024 * 1024:
        findings.append({"rule": "source_tree_exceeds_20_MiB"})
    history_blobs = 0
    for line in git("rev-list", "--objects", "--all", "--reflog", allow_unborn=True).splitlines():
        raw_sha, _, raw_path = line.partition(b" ")
        if git("cat-file", "-t", raw_sha.decode()).strip() != b"blob":
            continue
        history_blobs += 1
        inspect_blob(raw_path.decode("utf-8", errors="replace") or "<history blob>", git("cat-file", "blob", raw_sha.decode()), findings)
    commits = git("rev-list", "--all", "--count", allow_unborn=True).decode().strip()
    report = {"scope": "staged_index_and_all_local_history" if args.staged else "candidate_source_and_all_local_history",
              "findings": findings, "files": files, "source_bytes": sum(r["bytes"] for r in files),
              "history_commits": int(commits or 0), "history_blobs_scanned": history_blobs,
              "test_credentials": "Explicit test-only example credentials remain safe test fixtures; no real environment/database payload is included.",
              "limitations": "Pattern/denylist review plus independent source inspection; not a guarantee against every credential format."}
    destination = ROOT / args.report
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("files", "test_credentials", "limitations")}, indent=2))
    print("Source files reviewed:", len(files))
    raise SystemExit(1 if findings else 0)


if __name__ == "__main__":
    main()
