import hashlib
import mimetypes
from pathlib import Path

from app.config import SUPPORTED
from app.core.extractor import extract_text
from app.core.intelligence import extract_clues, infer_category


class Scanner:
    """Reliable metadata-first document scanner.

    A document is catalogued before content extraction is attempted. An
    extraction failure therefore never makes a discovered document disappear.
    The Database instance must be created in the worker thread.
    """

    def __init__(self, db, progress=None):
        self.db = db
        self.progress = progress

    def hash_file(self, path):
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                data = f.read(1024 * 1024)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()

    def _folder_id(self, folder):
        row = self.db.one("SELECT id FROM folders WHERE path=?", (str(folder),))
        if row:
            return row["id"]
        return self.db.execute(
            "INSERT INTO folders(path) VALUES(?)", (str(folder),)
        ).lastrowid

    def _catalog_file(self, folder_id, path, stat, old, digest, mime):
        path_text = str(path)
        if old:
            self.db.execute(
                """UPDATE documents SET
                   folder_id=?, name=?, extension=?, size=?, modified_at=?,
                   sha256=?, mime_type=?, missing=0
                   WHERE id=?""",
                (
                    folder_id, path.name, path.suffix.lower(), stat.st_size,
                    stat.st_mtime, digest, mime, old["id"],
                ),
            )
            return old["id"]

        return self.db.execute(
            """INSERT INTO documents(
                folder_id,path,name,extension,size,modified_at,sha256,
                mime_type,page_count,width,height,text,title,category,
                importance,needs_review,missing,scan_status,scan_error
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                folder_id, path_text, path.name, path.suffix.lower(),
                stat.st_size, stat.st_mtime, digest, mime,
                0, 0, 0, "", path.stem, "General", "Normal", 1, 0,
                "Indexing", "",
            ),
        ).lastrowid

    def _set_scan_state(self, doc_id, status, error=""):
        self.db.execute(
            "UPDATE documents SET scan_status=?, scan_error=? WHERE id=?",
            (status, error, doc_id),
        )

    def scan_folder(self, folder):
        folder = Path(folder).expanduser().resolve()
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))

        folder_id = self._folder_id(folder)
        paths = sorted(
            (
                p for p in folder.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED
            ),
            key=lambda p: str(p).lower(),
        )
        total = len(paths)

        result = {
            "folder": str(folder),
            "discovered": total,
            "indexed": 0,
            "unchanged": 0,
            "failed": 0,
            "errors": [],
        }

        if self.progress:
            self.progress(0, total, "Preparing scan…")

        for i, path in enumerate(paths, 1):
            path_text = str(path)
            try:
                stat = path.stat()
                old = self.db.one(
                    "SELECT * FROM documents WHERE path=?", (path_text,)
                )

                if (
                    old
                    and old["size"] == stat.st_size
                    and old["modified_at"] == stat.st_mtime
                ):
                    self.db.execute(
                        """UPDATE documents
                           SET missing=0, folder_id=?
                           WHERE id=?""",
                        (folder_id, old["id"]),
                    )
                    # If a previous scan failed, don't erase that information
                    # merely because the file has not changed.
                    result["unchanged"] += 1
                    continue

                try:
                    digest = self.hash_file(path)
                    hash_error = ""
                except Exception as exc:
                    digest = old["sha256"] if old else ""
                    hash_error = f"{type(exc).__name__}: {exc}"

                mime = mimetypes.guess_type(path_text)[0] or ""

                # IMPORTANT: catalogue first. Extraction can never prevent
                # the file from appearing in the Library.
                doc_id = self._catalog_file(
                    folder_id, path, stat, old, digest, mime
                )

                extraction_error = None
                try:
                    text, pages, width, height = extract_text(path)
                except Exception as exc:
                    text = ""
                    pages = width = height = 0
                    extraction_error = f"{type(exc).__name__}: {exc}"

                if extraction_error:
                    category = infer_category(path, "") or "General"
                    self.db.execute(
                        """UPDATE documents SET
                           page_count=?, width=?, height=?, text=?,
                           title=?, category=?, missing=0, needs_review=1
                           WHERE id=?""",
                        (
                            pages, width, height, text, path.stem,
                            category, doc_id,
                        ),
                    )
                    detail = f"Extraction failed: {extraction_error}"
                    if hash_error:
                        detail += f" | Hash failed: {hash_error}"
                    self._set_scan_state(doc_id, "Extraction failed", detail)
                    self.db.execute(
                        """INSERT INTO activity(document_id,action,detail)
                           VALUES(?,?,?)""",
                        (doc_id, "extraction_failed", detail),
                    )
                    result["failed"] += 1
                    result["errors"].append((path_text, detail))
                    continue

                category = infer_category(path, text) or "General"
                self.db.execute(
                    """UPDATE documents SET
                       page_count=?, width=?, height=?, text=?,
                       title=?, category=?, missing=0, needs_review=1
                       WHERE id=?""",
                    (
                        pages, width, height, text, path.stem,
                        category, doc_id,
                    ),
                )

                self.db.execute(
                    "DELETE FROM clues WHERE document_id=?", (doc_id,)
                )
                try:
                    clues = [
                        (doc_id, clue_type, value)
                        for clue_type, value in extract_clues(text)
                    ]
                    if clues:
                        self.db.executemany(
                            """INSERT INTO clues(
                               document_id,clue_type,value
                               ) VALUES(?,?,?)""",
                            clues,
                        )
                except Exception as exc:
                    result["errors"].append(
                        (path_text, f"Clue extraction failed: {exc}")
                    )

                status = "Indexed"
                if hash_error:
                    status = "Indexed (hash warning)"
                self._set_scan_state(doc_id, status, hash_error)
                self.db.execute(
                    """INSERT INTO activity(document_id,action,detail)
                       VALUES(?,?,?)""",
                    (doc_id, "indexed", path_text),
                )
                result["indexed"] += 1

            except Exception as exc:
                # Keep the scan alive, but make the failure visible.
                message = f"{type(exc).__name__}: {exc}"
                result["failed"] += 1
                result["errors"].append((path_text, message))

                # If a row already exists, preserve it and record the failure.
                try:
                    row = self.db.one(
                        "SELECT id FROM documents WHERE path=?", (path_text,)
                    )
                    if row:
                        self._set_scan_state(row["id"], "Scan failed", message)
                        self.db.execute(
                            """INSERT INTO activity(
                               document_id,action,detail) VALUES(?,?,?)""",
                            (row["id"], "scan_failed", message),
                        )
                except Exception:
                    pass
            finally:
                if self.progress:
                    self.progress(i, total, path.name)

        if paths:
            placeholders = ",".join("?" for _ in paths)
            self.db.execute(
                f"""UPDATE documents SET missing=1
                    WHERE folder_id=? AND path NOT IN ({placeholders})""",
                [folder_id] + [str(p) for p in paths],
            )
        else:
            self.db.execute(
                "UPDATE documents SET missing=1 WHERE folder_id=?",
                (folder_id,),
            )

        self.db.execute(
            "UPDATE folders SET last_scan=CURRENT_TIMESTAMP WHERE id=?",
            (folder_id,),
        )
        return result
