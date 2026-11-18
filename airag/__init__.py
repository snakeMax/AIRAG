"""AIRAG - AI Research Article Generation."""
__version__ = "0.4.0"
__repo__ = "snakeMax/AIRAG"  # GitHub repo used for update checks
__app_name__ = "AIRAG"


def build_info() -> dict:
    """Which kind of build this is: "release", "test" (pre-release test builds) or "source".
    Test builds get a small build_info.json from the Android test workflow."""
    import json
    import os
    import sys
    from pathlib import Path
    f = Path(__file__).with_name("build_info.json")
    if f.exists():
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
            return {"channel": str(info.get("channel") or "test"), "commit": str(info.get("commit") or "")[:7]}
        except (OSError, ValueError):
            pass
    frozen = bool(getattr(sys, "frozen", False)) or os.environ.get("AIRAG_PLATFORM") == "android"
    return {"channel": "release" if frozen else "source", "commit": ""}
