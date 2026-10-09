# JASS Document Detective — v1.3.2 Reliable Investigation Studio

A local-first PySide6 document catalog and investigation workspace.

## v1.3.2 upgrade

This release fixes the background folder scanner's SQLite threading failure.

### Important architecture fix

The GUI and scanner no longer share a SQLite connection across threads.

```text
GUI thread
   │
   └── Database connection #1

Scan worker thread
   │
   └── Database connection #2
          │
          └── same SQLite database file (WAL mode)
```

The worker creates and closes its own connection inside `QThread.run()`.
`check_same_thread=False` is **not** used.

#

### Scan reliability fixes in v1.3.2

The v1.3.2 scanner is **metadata-first**:

1. Discover supported files.
2. Catalogue filesystem metadata immediately.
3. Attempt hashing and content extraction.
4. Record extraction/scan failures on the document.
5. Keep failed documents visible in the Library.
6. Refresh the Library automatically when the scan completes.

The scan summary reports:

```text
Found → Indexed → Unchanged → Failed
```

A corrupt or password-protected document is therefore not silently lost from the catalogue.

The database migration adds:

- `scan_status`
- `scan_error`

Existing databases are migrated automatically. No database reset is required.

## Folder scanning

- Select a folder with **Add Folder**.
- The folder is scanned recursively.
- PDF, Office, text, spreadsheet, presentation and image files are catalogued.
- Existing unchanged files are handled by a fast metadata path.
- Changed files are re-indexed.
- SHA-256 hashes are calculated for changed/new files.
- Text and document metadata are extracted where supported.
- Detective clues and categories are regenerated.
- Missing files are marked instead of silently removed.
- Library/dashboard refreshes after a successful scan.
- Progress is reported for every discovered document.
- A single unreadable file does not abort the complete scan.
- Failed extraction remains visible with its error status.

## Run

From the project root:

```powershell
cd D:\Github\JASS-Investigation-Studio
python app\main.py
```

Or from inside `app`:

```powershell
python main.py
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Main capabilities

- Document Library
- Search / FTS5
- Folder indexing
- PDF/image preview
- Extracted text
- Review queue
- Favorites
- Duplicate Detective
- Archive Health
- Tags
- Cases
- Evidence Board
- Document comparison
- Conflict detection
- Case timeline
- Investigation notes
- Optional Tesseract OCR
- CSV/JSON export
- SQLite backup

## Data

The local database is stored under:

```text
app/../data/document_detective.db
```

The application is local-first and does not require a cloud service.
