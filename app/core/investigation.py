
import re
import shutil
import subprocess
from pathlib import Path

class InvestigationService:
    def __init__(self, db, document_service):
        self.db = db
        self.documents = document_service

    def ensure_case(self, name, description=""):
        self.db.execute(
            "INSERT OR IGNORE INTO collections(name,description) VALUES(?,?)",
            (name, description)
        )
        return self.db.one("SELECT * FROM collections WHERE name=?", (name,))

    def add_evidence(self, case_id, document_id):
        self.db.execute(
            "INSERT OR IGNORE INTO collection_documents(collection_id,document_id) VALUES(?,?)",
            (case_id, document_id)
        )

    def remove_evidence(self, case_id, document_id):
        self.db.execute(
            "DELETE FROM collection_documents WHERE collection_id=? AND document_id=?",
            (case_id, document_id)
        )

    def case_documents(self, case_id):
        return self.db.query("""
            SELECT d.* FROM documents d
            JOIN collection_documents cd ON cd.document_id=d.id
            WHERE cd.collection_id=?
            ORDER BY d.modified_at DESC
        """, (case_id,))

    def create_relation(self, a, b, relation="related"):
        if a == b:
            return
        self.db.execute(
            "INSERT OR IGNORE INTO document_relations(document_id,related_id,relation) VALUES(?,?,?)",
            (a,b,relation)
        )
        self.db.execute(
            "INSERT OR IGNORE INTO document_relations(document_id,related_id,relation) VALUES(?,?,?)",
            (b,a,relation)
        )

    def relations(self, doc_id):
        return self.db.query("""
            SELECT r.related_id,r.relation,d.name,d.title,d.category
            FROM document_relations r JOIN documents d ON d.id=r.related_id
            WHERE r.document_id=? ORDER BY d.name
        """, (doc_id,))

    def conflicts(self, doc_ids):
        """Find same clue types whose values differ across selected evidence."""
        if not doc_ids:
            return []
        marks = ",".join("?" for _ in doc_ids)
        rows = self.db.query(f"""
            SELECT document_id,clue_type,value
            FROM clues
            WHERE document_id IN ({marks})
            ORDER BY clue_type,value
        """, doc_ids)
        grouped = {}
        for r in rows:
            grouped.setdefault(r["clue_type"], {}).setdefault(r["value"], []).append(r["document_id"])
        result=[]
        for typ, values in grouped.items():
            if len(values) > 1:
                result.append((typ, list(values.items())))
        return result

    def timeline(self, doc_ids):
        if not doc_ids:
            return []
        marks=",".join("?" for _ in doc_ids)
        rows=self.db.query(f"""
            SELECT d.id,d.name,d.title,c.value
            FROM clues c JOIN documents d ON d.id=c.document_id
            WHERE c.document_id IN ({marks}) AND c.clue_type='year'
            ORDER BY c.value,d.name
        """, doc_ids)
        return rows

    def case_stats(self, case_id):
        docs=self.case_documents(case_id)
        total_size=sum(d["size"] or 0 for d in docs)
        categories={}
        for d in docs:
            categories[d["category"]]=categories.get(d["category"],0)+1
        return len(docs), total_size, categories

    def run_ocr(self, image_path):
        """Optional OCR via the external Tesseract executable."""
        image_path=str(image_path)
        try:
            proc=subprocess.run(
                ["tesseract", image_path, "stdout", "--psm", "3"],
                capture_output=True, text=True, encoding="utf-8", errors="ignore",
                timeout=120
            )
            if proc.returncode == 0:
                return proc.stdout.strip(), ""
            return "", proc.stderr.strip() or "Tesseract returned an error."
        except FileNotFoundError:
            return "", "Tesseract was not found on PATH."
        except Exception as exc:
            return "", str(exc)

    def append_ocr_text(self, doc_id, text):
        doc=self.documents.get(doc_id)
        if not doc or not text.strip():
            return
        combined=(doc["text"] or "").strip()
        marker="\n\n[OCR]\n"
        if "[OCR]" not in combined:
            combined += marker + text.strip()
        else:
            combined += "\n" + text.strip()
        self.db.execute("UPDATE documents SET text=?,needs_review=1 WHERE id=?", (combined,doc_id))
        self.db.execute(
            "INSERT INTO activity(document_id,action,detail) VALUES(?,?,?)",
            (doc_id,"ocr",f"Added {len(text)} OCR characters")
        )
        self.db.execute("INSERT INTO clues(document_id,clue_type,value) VALUES(?,?,?)",
                         (doc_id,"ocr","OCR text added"))
