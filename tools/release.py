"""Publish a new version.

    python tools/release.py 0.2.1

1. writes the version into airag/__init__.py
2. makes sure CHANGELOG.md has a section for it (adds an empty one to fill in)
3. commits and pushes - GitHub Actions sees the new version, builds the installer and
   publishes release v0.2.1. Installed copies of AIRAG offer the update on next start.
"""
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1].lstrip("v")):
        sys.exit("usage: python tools/release.py 1.2.3")
    v = sys.argv[1].lstrip("v")
    if git("status", "--porcelain"):
        sys.exit("Commit or stash your changes first.")
    init = ROOT / "airag" / "__init__.py"
    init.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{v}"', init.read_text(encoding="utf-8")), encoding="utf-8")
    log = ROOT / "CHANGELOG.md"
    text = log.read_text(encoding="utf-8")
    if f"## [{v}]" not in text:
        head, _, rest = text.partition("\n## ")
        text = f"{head}\n## [{v}] - {date.today().isoformat()}\n\n- \n\n## {rest}" if rest else f"{text}\n## [{v}] - {date.today()}\n\n- \n"
        log.write_text(text, encoding="utf-8")
        input(f"Added a CHANGELOG.md section for {v}. Fill it in, save, then press Enter to continue...")
    if subprocess.run([sys.executable, str(ROOT / "tools" / "check_secrets.py")]).returncode:
        sys.exit("Fix the secrets problem first.")
    git("add", "airag/__init__.py", "CHANGELOG.md")
    git("commit", "-m", f"Release v{v}")
    git("push", "origin", "HEAD:main")
    print(f"Pushed v{v}. Follow the build at https://github.com/snakeMax/AIRAG/actions")


if __name__ == "__main__":
    main()
