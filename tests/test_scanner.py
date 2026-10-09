import tempfile
from pathlib import Path

from app.core.database import Database
from app.core.scanner import Scanner


def test_scan_catalogues_bad_pdf_and_good_text():
    root = Path(tempfile.mkdtemp())
    (root / "good.txt").write_text("A normal document.", encoding="utf-8")
    (root / "broken.pdf").write_bytes(b"not a real PDF")

    db = Database(root / "test.db")
    result = Scanner(db).scan_folder(root)

    assert result["discovered"] == 2
    assert result["indexed"] == 1
    assert result["failed"] == 1

    rows = db.query(
        "SELECT name, scan_status, missing FROM documents ORDER BY name"
    )
    assert len(rows) == 2
    assert rows[0]["name"] == "broken.pdf"
    assert rows[0]["scan_status"] == "Extraction failed"
    assert rows[0]["missing"] == 0
    assert rows[1]["name"] == "good.txt"
    assert rows[1]["scan_status"] == "Indexed"
