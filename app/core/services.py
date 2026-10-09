import csv,json,shutil
from pathlib import Path
from app.core.intelligence import timeline_events

class DocumentService:
    def __init__(self,db):self.db=db
    def documents(self,query="",filter_name="All",category="All"):
        cond=[]; params=[]
        mapping={"Favorites":"d.is_favorite=1","Review":"d.needs_review=1","Missing":"d.missing=1","Duplicates":"""d.sha256 IN
        (SELECT sha256 FROM documents GROUP BY sha256 HAVING COUNT(*)>1)"""}
        if filter_name in mapping:cond.append(mapping[filter_name])
        extmap={"PDFs":[".pdf"],"Images":[".jpg",".jpeg",".png",".bmp",".gif",".tif",".tiff",".webp"],
                "Office":[".docx",".xlsx",".xlsm",".pptx"],"Text":[".txt",".md",".markdown",".csv",".html",".htm"]}
        if filter_name in extmap:
            cond.append("d.extension IN ("+",".join("?"*len(extmap[filter_name]))+")");params.extend(extmap[filter_name])
        if category!="All":cond.append("d.category=?");params.append(category)
        if query.strip():
            q="* "+query.replace('"',' ')+" *"
            sql="SELECT d.* FROM documents d JOIN documents_fts f ON f.rowid=d.id WHERE documents_fts MATCH ?"
            params=[q]+params
            if cond:sql+=" AND "+" AND ".join(cond)
            return self.db.query(sql+" ORDER BY COALESCE(d.last_opened,0) DESC,d.modified_at DESC",params)
        where=(" WHERE "+" AND ".join(cond)) if cond else ""
        return self.db.query("SELECT d.* FROM documents d"+where+" ORDER BY COALESCE(d.last_opened,0) DESC,d.modified_at DESC",params)
    def get(self,id):return self.db.one("SELECT * FROM documents WHERE id=?",(id,))
    def toggle(self,id,field):self.db.execute(f"UPDATE documents SET {field}=1-{field} WHERE id=?",(id,))
    def reviewed(self,id):self.db.execute("UPDATE documents SET needs_review=0 WHERE id=?",(id,))
    def importance(self,id,value):self.db.execute("UPDATE documents SET importance=? WHERE id=?",(value,id))
    def note(self,id,value):self.db.execute("UPDATE documents SET notes=? WHERE id=?",(value,id))
    def title(self,id,value):self.db.execute("UPDATE documents SET title=? WHERE id=?",(value,id))
    def add_tag(self,id,name):
        name=name.strip()
        if not name:return
        self.db.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)",(name,))
        tid=self.db.one("SELECT id FROM tags WHERE name=?",(name,))["id"]
        self.db.execute("INSERT OR IGNORE INTO document_tags(document_id,tag_id) VALUES(?,?)",(id,tid))
    def tags(self,id):return [r["name"] for r in self.db.query("SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id=t.id WHERE dt.document_id=? ORDER BY t.name",(id,))]
    def clues(self,id):return self.db.query("SELECT clue_type,value FROM clues WHERE document_id=? ORDER BY clue_type,value",(id,))
    def activity(self,id):return self.db.query("SELECT action,detail,created_at FROM activity WHERE document_id=? ORDER BY id DESC LIMIT 50",(id,))
    def related(self,id):
        doc=self.get(id)
        if not doc:return []
        clues={r["value"].lower() for r in self.clues(id)}
        if not clues:return []
        rows=self.db.query("SELECT * FROM documents WHERE id<>? AND missing=0 ORDER BY modified_at DESC",(id,))
        scored=[]
        for r in rows:
            vals={x["value"].lower() for x in self.clues(r["id"])}
            common=clues & vals
            if common:scored.append((len(common),r,common))
        scored.sort(key=lambda x:(-x[0],-float(x[1]["modified_at"] or 0)))
        return scored[:12]
    def timeline(self,id):
        d=self.get(id)
        if not d:return []
        import re
        years=sorted(set(re.findall(r"\b(?:19|20)\d{2}\b",d["text"] or "")))
        return [(y,"Mentioned in this document") for y in years]
    def stats(self):
        return {k:self.db.one(sql)["n"] for k,sql in {
            "documents":"SELECT COUNT(*) n FROM documents",
            "storage":"SELECT COALESCE(SUM(size),0) n FROM documents",
            "favorites":"SELECT COUNT(*) n FROM documents WHERE is_favorite=1",
            "review":"SELECT COUNT(*) n FROM documents WHERE needs_review=1",
            "missing":"SELECT COUNT(*) n FROM documents WHERE missing=1",
            "duplicates":"""SELECT COUNT(*) n FROM documents WHERE sha256 IN
            (SELECT sha256 FROM documents WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1)"""
        }.items()}
    def categories(self):return self.db.query("SELECT category,COUNT(*) n FROM documents GROUP BY category ORDER BY n DESC")
    def recent(self,limit=10):return self.db.query("SELECT * FROM documents ORDER BY COALESCE(last_opened,0) DESC,modified_at DESC LIMIT ?",(limit,))
    def duplicate_groups(self):return self.db.query("""SELECT sha256,COUNT(*) count,SUM(size) total_size,GROUP_CONCAT(name,' | ') names FROM documents
        WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1 ORDER BY count DESC""")
    def collections(self):return self.db.query("""SELECT c.id,c.name,c.description,COUNT(cd.document_id) n FROM collections c
        LEFT JOIN collection_documents cd ON cd.collection_id=c.id GROUP BY c.id ORDER BY c.name""")
    def create_collection(self,name,description=""):self.db.execute("INSERT OR IGNORE INTO collections(name,description) VALUES(?,?)",(name,description))
    def export_csv(self,path):
        rows=self.db.query("SELECT id,title,name,category,importance,path,extension,size,modified_at,sha256,needs_review,is_favorite,missing FROM documents")
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f);w.writerow(rows[0].keys() if rows else ["id"]);[w.writerow(list(r)) for r in rows]
    def export_json(self,path):
        rows=self.db.query("SELECT * FROM documents");Path(path).write_text(json.dumps([dict(r) for r in rows],indent=2,default=str),encoding="utf-8")
    def backup(self,path):self.db.conn.commit();shutil.copy2(self.db.path,path)
