from __future__ import annotations

import re
import sys
from pathlib import Path


HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\b")
PRESERVED_COLORS = {
    "#9fcdbd",  # muted mint
    "#e4c96a",  # muted yellow and month labels
    "#2f3437",
    "#d9dddb",
    "#78aa9b",
    "#c5aa52",
    "#777d80",
    "#f1f2ef",
    "#aeb5b2",
}


def grayscale(match: re.Match[str]) -> str:
    if match.group().lower() in PRESERVED_COLORS:
        return match.group()
    value = match.group()[1:]
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    luminance = round(0.2126 * red + 0.7152 * green + 0.0722 * blue)
    channel = f"{luminance:02x}"
    return f"#{channel}{channel}{channel}"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: grayscale_svg.py SVG_PATH", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        raise FileNotFoundError(f"Generated SVG not found: {path}")

    source = path.read_text(encoding="utf-8")
    converted, count = HEX_COLOR.subn(grayscale, source)
    if count == 0:
        raise RuntimeError("No colors were found in the generated SVG")

    path.write_text(converted, encoding="utf-8")
    print(f"Converted {count} color values to grayscale in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
