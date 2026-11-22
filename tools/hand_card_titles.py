"""Apply the measured title edits to the mobile edition's captured Secret Technique cards."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from card_titles import TITLE_ATLAS

PACKAGE = "15"
WIDTH = 404
HEIGHT = 564
BLOCK_SIDE = 4
BLOCK_BYTES = 16
ROW_BYTES = WIDTH // BLOCK_SIDE * BLOCK_BYTES
RAW_SIZE = ROW_BYTES * (HEIGHT // BLOCK_SIDE)


@dataclass(frozen=True)
class TitleEdit:
    source: str
    target: str
    # Bounds in ASTC blocks, in the texture's stored (bottom-up) order.
    box: tuple[int, int, int, int]
    blocks: bytes

    def apply(self, raw: bytes) -> bytes | None:
        """Replace the title blocks on a known capture, or report an unmeasured revision."""
        digest = sha256(raw).hexdigest()
        if digest == self.target:
            return raw
        if len(raw) != RAW_SIZE or digest != self.source:
            return None
        x0, y0, x1, y1 = self.box
        span = (x1 - x0) * BLOCK_BYTES
        if not (0 <= x0 < x1 <= WIDTH // BLOCK_SIDE and 0 <= y0 < y1 <= HEIGHT // BLOCK_SIDE
                and len(self.blocks) == (y1 - y0) * span):
            return None
        patched = bytearray(raw)
        for row in range(y0, y1):
            start = row * ROW_BYTES + x0 * BLOCK_BYTES
            offset = (row - y0) * span
            patched[start:start + span] = self.blocks[offset:offset + span]
        return bytes(patched) if sha256(patched).hexdigest() == self.target else None


def load_edits(catalog_dir: Path) -> dict[int, TitleEdit]:
    """Read the shared English title art that both patch languages use on these cards."""
    folder = catalog_dir.parent / "sprites" / f"{TITLE_ATLAS:016X}"
    manifest = folder / "hand_titles.json"
    if not manifest.is_file():
        return {}
    records = json.loads(manifest.read_text(encoding="utf-8"))
    blocks = (folder / "hand_titles.blocks").read_bytes()
    edits = {}
    for asset, record in records.items():
        offset = record["offset"]
        edits[int(asset, 16)] = TitleEdit(record["source"], record["target"], tuple(record["box"]),
                                        blocks[offset:offset + record["size"]])
    return edits
