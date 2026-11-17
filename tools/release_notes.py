"""Print the CHANGELOG.md section for a version (used for the GitHub release text)."""
import re
import sys
from pathlib import Path

version = sys.argv[1].lstrip("v")
text = Path(__file__).resolve().parent.parent.joinpath("CHANGELOG.md").read_text(encoding="utf-8")
m = re.search(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
body = m.group(1).strip() if m else f"AIRAG {version}"
print(body + "\n\n---\n**Install:** download `AIRAG-Setup-" + version + ".exe` below and run it. "
      "Already installed? AIRAG will offer the update automatically.\n"
      "**Portable:** unzip `AIRAG-" + version + "-portable-win64.zip` anywhere and run `AIRAG.exe`.")
