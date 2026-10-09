import sqlite3
from pathlib import Path
from app.config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS folders(
 id INTEGER PRIMARY KEY,
 path TEXT UNIQUE NOT NULL,
 added_at TEXT DEFAULT CURRENT_TIMESTAMP,
 last_scan TEXT
);

CREATE TABLE IF NOT EXISTS documents(
 id INTEGER PRIMARY KEY,
 folder_id INTEGER,
 path TEXT UNIQUE NOT NULL,
 name TEXT NOT NULL,
 extension TEXT,
 size INTEGER DEFAULT 0,
 modified_at REAL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 sha256 TEXT,
 mime_type TEXT,
 page_count INTEGER DEFAULT 0,
 width INTEGER DEFAULT 0,
 height INTEGER DEFAULT 0,
 text TEXT DEFAULT '',
 title TEXT DEFAULT '',
 category TEXT DEFAULT 'General',
 importance TEXT DEFAULT 'Normal',
 needs_review INTEGER DEFAULT 1,
 is_favorite INTEGER DEFAULT 0,
 is_archived INTEGER DEFAULT 0,
 missing INTEGER DEFAULT 0,
 notes TEXT DEFAULT '',
 last_opened REAL,
 FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tags(
 id INTEGER PRIMARY KEY,
 name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_tags(
 document_id INTEGER NOT NULL,
 tag_id INTEGER NOT NULL,
 PRIMARY KEY(document_id,tag_id),
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
 FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS collections(
 id INTEGER PRIMARY KEY,
 name TEXT UNIQUE NOT NULL,
 description TEXT DEFAULT '',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_documents(
 collection_id INTEGER NOT NULL,
 document_id INTEGER NOT NULL,
 PRIMARY KEY(collection_id,document_id),
 FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE,
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_relations(
 document_id INTEGER NOT NULL,
 related_id INTEGER NOT NULL,
 relation TEXT DEFAULT 'related',
 PRIMARY KEY(document_id,related_id),
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
 FOREIGN KEY(related_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS clues(
 id INTEGER PRIMARY KEY,
 document_id INTEGER NOT NULL,
 clue_type TEXT NOT NULL,
 value TEXT NOT NULL,
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity(
 id INTEGER PRIMARY KEY,
 document_id INTEGER,
 action TEXT NOT NULL,
 detail TEXT DEFAULT '',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
 name,path,text,title,category,
 content='documents',content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
 INSERT INTO documents_fts(rowid,name,path,text,title,category)
 VALUES(new.id,new.name,new.path,new.text,new.title,new.category);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
 INSERT INTO documents_fts(documents_fts,rowid,name,path,text,title,category)
 VALUES('delete',old.id,old.name,old.path,old.text,old.title,old.category);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
 INSERT INTO documents_fts(documents_fts,rowid,name,path,text,title,category)
 VALUES('delete',old.id,old.name,old.path,old.text,old.title,old.category);
 INSERT INTO documents_fts(rowid,name,path,text,title,category)
 VALUES(new.id,new.name,new.path,new.text,new.title,new.category);
END;
"""

class Database:
    def __init__(self,path=DB_PATH):
        self.path=Path(path)
        self.conn=sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory=sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        cols={r["name"] for r in self.conn.execute("PRAGMA table_info(documents)")}
        wanted={
            "title":"TEXT DEFAULT ''","category":"TEXT DEFAULT 'General'",
            "importance":"TEXT DEFAULT 'Normal'","needs_review":"INTEGER DEFAULT 1",
            "last_opened":"REAL",
            "scan_status":"TEXT DEFAULT 'Ready'",
            "scan_error":"TEXT DEFAULT ''"
        }
        for name,definition in wanted.items():
            if name not in cols:
                self.conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")

    def rebuild_fts(self):
        self.conn.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")
        self.conn.commit()

    def execute(self,sql,params=()):
        cur=self.conn.execute(sql,params); self.conn.commit(); return cur
    def executemany(self,sql,rows):
        cur=self.conn.executemany(sql,rows); self.conn.commit(); return cur
    def query(self,sql,params=()): return self.conn.execute(sql,params).fetchall()
    def one(self,sql,params=()): return self.conn.execute(sql,params).fetchone()
    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
