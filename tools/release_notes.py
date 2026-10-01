"""Print the CHANGELOG.md section of a version (used as the GitHub release text).

    python tools/release_notes.py 0.4.1
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def notes(version: str) -> str:
    try:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lstrip("vV") == version
            continue
        if inside:
            lines.append(line)
    body = "\n".join(lines).strip()
    return body or f"KMuted {version}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes(sys.argv[1]))
