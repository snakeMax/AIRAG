"""Fail if anything that looks like an API key or a private settings file is tracked by git.
Run in CI and before releases:  python tools/check_secrets.py"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI key": r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}",
    "Google API key": r"AIza[0-9A-Za-z_\-]{35}",
    "GitHub token": r"(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}",
    "Brave key": r"\bBSA[A-Za-z0-9_\-]{25,}",
    "Private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}
BAD_FILES = re.compile(r"(^|/)(settings\.json|\.env(\..*)?|.*\.pem|.*\.jks|.*\.keystore|ANDROID_KEY.*\.txt|signing/.*)$")


def tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l]
    except Exception:
        return [str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*")
                if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts]


def main() -> int:
    problems = []
    for rel in tracked():
        if BAD_FILES.search(rel):
            problems.append(f"{rel}: private file must not be committed")
            continue
        p = ROOT / rel
        if p.suffix.lower() in (".png", ".ico", ".exe", ".zip", ".pyc"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, text):
                problems.append(f"{rel}: possible {name} ({m.group(0)[:8]}…)")
    if problems:
        print("Possible secrets found:\n  " + "\n  ".join(problems))
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
