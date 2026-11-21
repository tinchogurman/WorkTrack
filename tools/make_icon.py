"""Generate assets/worktrack.ico from the icon drawn in worktrack/ui/icons.py.

Writes a multi-size ICO (PNG-compressed entries, supported since Windows Vista).
Usage: .venv\\Scripts\\python.exe tools\\make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from worktrack.ui.icons import app_icon  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(icon, size: int) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    icon.pixmap(QSize(size, size)).toImage().save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path: Path, images: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO directory
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    path.write_bytes(header + entries + blobs)


def main() -> None:
    QApplication([])
    icon = app_icon(active=False)
    target = ROOT / "assets" / "worktrack.ico"
    target.parent.mkdir(exist_ok=True)
    write_ico(target, [(s, png_bytes(icon, s)) for s in SIZES])
    print(f"Icon written: {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
