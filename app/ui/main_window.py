
import sys, subprocess, time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QRectF, QPointF
from PySide6.QtGui import QDesktopServices, QPixmap, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QTextEdit, QStackedWidget, QFrame, QStatusBar, QInputDialog, QTabWidget,
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QScrollArea, QSpinBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem
)

from app.config import APP_NAME, APP_VERSION, IMAGE_EXTENSIONS
from app.core.database import Database
from app.core.scanner import Scanner
from app.core.services import DocumentService
from app.core.extractor import render_pdf_page
from app.core.investigation import InvestigationService


class Worker(QThread):
    """Background scanner with a SQLite connection owned by this thread."""
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, db_path, folder):
        super().__init__()
        self.db_path = Path(db_path)
        self.folder = folder

    def run(self):
        worker_db = None
        try:
            # IMPORTANT: create SQLite connection inside the worker thread.
            worker_db = Database(self.db_path)
            result = Scanner(worker_db, self.progress.emit).scan_folder(self.folder)
            self.done.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if worker_db is not None:
                worker_db.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {APP_VERSION}")
        self.resize(1600,950)
        self.db=Database()
        self.service=DocumentService(self.db)
        self.investigation=InvestigationService(self.db,self.service)
        self.current_filter="All"
        self.current_category="All"
        self.current_case_id=None
        self.current_id=None
        self.worker=None
        self.build()
        self.style()
        self.refresh_all()

    def build(self):
        central=QWidget()
        self.setCentralWidget(central)
        root=QVBoxLayout(central)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)

        top=QFrame(objectName="topbar")
        tl=QHBoxLayout(top)
        tl.setContentsMargins(18,10,18,10)
        brand=QLabel("JASS  /  DOCUMENT DETECTIVE")
        brand.setObjectName("brand")
        tl.addWidget(brand)
        badge=QLabel("INVESTIGATION STUDIO")
        badge.setObjectName("badge")
        tl.addWidget(badge)
        tl.addStretch()
        self.search=QLineEdit()
        self.search.setPlaceholderText("Search filename, extracted text, names, references, dates…")
        self.search.returnPressed.connect(self.refresh_library)
        tl.addWidget(self.search,1)
        b=QPushButton("Search")
        b.clicked.connect(self.refresh_library)
        tl.addWidget(b)
        root.addWidget(top)

        split=QSplitter()
        root.addWidget(split,1)

        side=QFrame(objectName="sidebar")
        sl=QVBoxLayout(side)
        sl.setContentsMargins(12,18,12,12)
        sl.addWidget(QLabel("WORKSPACE",objectName="navtitle"))
        self.nav=QListWidget()
        items=[
            ("⌂","Dashboard"),("▦","Library"),("◉","Review Queue"),
            ("★","Favorites"),("♊","Duplicates"),("◈","Archive Health"),
            ("🕵","Investigation Studio"),("🏷","Tags"),("▣","Cases"),("⚙","Settings")
        ]
        for icon,name in items:
            self.nav.addItem(QListWidgetItem(f"{icon}   {name}"))
        self.nav.currentRowChanged.connect(self.page)
        sl.addWidget(self.nav,1)
        for text,slot in [
            ("＋  Add Folder",self.add_folder),
            ("↻  Scan Again",self.scan_again),
            ("⇩  Export Index",self.export_index)
        ]:
            q=QPushButton(text);q.clicked.connect(slot);sl.addWidget(q)
        split.addWidget(side)

        self.pages=QStackedWidget()
        split.addWidget(self.pages)
        split.setSizes([235,1365])

        self.pages.addWidget(self.dashboard())
        self.pages.addWidget(self.library())
        self.pages.addWidget(self.queue("Review Queue",True))
        self.pages.addWidget(self.queue("Favorites",False))
        self.pages.addWidget(self.duplicates())
        self.pages.addWidget(self.health())
        self.pages.addWidget(self.investigation_page())
        self.pages.addWidget(self.tags())
        self.pages.addWidget(self.cases())
        self.pages.addWidget(self.settings())

        self.nav.setCurrentRow(0)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def dashboard(self):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(30,25,30,25)
        l.addWidget(QLabel("Document Command Center",objectName="pageTitle"))
        l.addWidget(QLabel(
            "A private document investigation environment — organize evidence, find connections and detect inconsistencies.",
            objectName="subtitle"))
        grid=QGridLayout()
        self.kpis={}
        specs=[
            ("documents","DOCUMENTS","Indexed files"),("storage","STORAGE","Original file footprint"),
            ("review","REVIEW","Awaiting review"),("duplicates","DUPLICATES","Exact-hash copies"),
            ("missing","MISSING","No longer on disk"),("favorites","FAVORITES","Marked important")
        ]
        for i,(key,label,tip) in enumerate(specs):
            f=QFrame(objectName="kpi");fl=QVBoxLayout(f)
            fl.addWidget(QLabel(label,objectName="kpiLabel"))
            v=QLabel("0",objectName="kpiValue");fl.addWidget(v)
            fl.addWidget(QLabel(tip,objectName="kpiTip"))
            self.kpis[key]=v
            grid.addWidget(f,i//3,i%3)
        l.addLayout(grid)
        row=QHBoxLayout()
        signals=QFrame(objectName="panel");sl=QVBoxLayout(signals)
        sl.addWidget(QLabel("ARCHIVE SIGNALS",objectName="sectionTitle"))
        self.signals=QLabel();self.signals.setWordWrap(True);sl.addWidget(self.signals);sl.addStretch()
        row.addWidget(signals,1)
        rec=QFrame(objectName="panel");rl=QVBoxLayout(rec)
        rl.addWidget(QLabel("RECENT DOCUMENTS",objectName="sectionTitle"))
        self.recent=QListWidget()
        self.recent.itemDoubleClicked.connect(lambda it:self.inspect(it.data(Qt.UserRole)))
        rl.addWidget(self.recent)
        row.addWidget(rec,2)
        l.addLayout(row,1)
        return w

    def library(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(24,22,24,22)
        h=QHBoxLayout();h.addWidget(QLabel("Document Library",objectName="pageTitle"));h.addStretch()
        self.libcount=QLabel(objectName="muted");h.addWidget(self.libcount);l.addLayout(h)
        f=QHBoxLayout();self.filters={}
        for name in ["All","PDFs","Images","Office","Text","Favorites","Review","Duplicates","Missing"]:
            b=QPushButton(name);b.setCheckable(True)
            b.clicked.connect(lambda _,n=name:self.set_filter(n))
            self.filters[name]=b;f.addWidget(b)
        self.category=QComboBox();self.category.currentIndexChanged.connect(self.set_category);f.addWidget(self.category);f.addStretch()
        l.addLayout(f)
        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(["Title / File","Category","Type","Size","Modified","Importance","Review","Status"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for i in range(1,8):self.table.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda _:self.inspect_selected())
        l.addWidget(self.table,1)
        return w

    def queue(self,title,review):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(28,25,28,25)
        l.addWidget(QLabel(title,objectName="pageTitle"))
        label=QLabel();l.addWidget(label)
        t=QTableWidget(0,5);t.setHorizontalHeaderLabels(["Title","Category","Type","Size","Status"])
        t.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        t.itemDoubleClicked.connect(lambda _:self.inspect_from(t))
        l.addWidget(t,1)
        if review:self.review_table=t;self.review_label=label
        else:self.favorite_table=t;self.favorite_label=label
        return w

    def duplicates(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(28,25,28,25)
        l.addWidget(QLabel("Duplicate Detective",objectName="pageTitle"))
        self.dupsummary=QLabel();l.addWidget(self.dupsummary)
        self.duptable=QTableWidget(0,4)
        self.duptable.setHorizontalHeaderLabels(["SHA-256","Copies","Reclaimable","Files"])
        self.duptable.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        l.addWidget(self.duptable,1)
        return w

    def health(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(28,25,28,25)
        l.addWidget(QLabel("Archive Health",objectName="pageTitle"))
        l.addWidget(QLabel("The archive should become progressively cleaner as you review, tag and investigate documents."))
        self.healthgrid=QGridLayout();l.addLayout(self.healthgrid);l.addStretch()
        return w

    def investigation_page(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(22,20,22,20)
        h=QHBoxLayout()
        h.addWidget(QLabel("Investigation Studio",objectName="pageTitle"));h.addStretch()
        self.case_combo=QComboBox();self.case_combo.currentIndexChanged.connect(self.load_case)
        h.addWidget(QLabel("Case:"));h.addWidget(self.case_combo)
        new=QPushButton("＋ New Case");new.clicked.connect(self.new_case);h.addWidget(new)
        l.addLayout(h)
        self.case_summary=QLabel("Create a case or select an existing one.");l.addWidget(self.case_summary)

        tabs=QTabWidget()
        self.board=EvidenceBoard()
        tabs.addTab(self.board,"Evidence Board")

        compare=QWidget();cl=QVBoxLayout(compare)
        ch=QHBoxLayout()
        self.left_doc=QComboBox();self.right_doc=QComboBox()
        compare_btn=QPushButton("Compare Documents");compare_btn.clicked.connect(self.compare_docs)
        ch.addWidget(self.left_doc,1);ch.addWidget(QLabel("VS"));ch.addWidget(self.right_doc,1);ch.addWidget(compare_btn)
        cl.addLayout(ch)
        self.compare_left=QTextEdit();self.compare_right=QTextEdit()
        self.compare_left.setReadOnly(True);self.compare_right.setReadOnly(True)
        cs=QSplitter(Qt.Horizontal);cs.addWidget(self.compare_left);cs.addWidget(self.compare_right);cl.addWidget(cs,1)
        tabs.addTab(compare,"Compare")

        conflicts=QWidget();fl=QVBoxLayout(conflicts)
        scan=QPushButton("Run Conflict Detector");scan.clicked.connect(self.run_conflicts);fl.addWidget(scan)
        self.conflict_table=QTableWidget(0,3)
        self.conflict_table.setHorizontalHeaderLabels(["Clue Type","Different Values","Evidence"])
        self.conflict_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.conflict_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
        fl.addWidget(self.conflict_table,1)
        tabs.addTab(conflicts,"Conflicts")

        timeline=QWidget();tl=QVBoxLayout(timeline)
        self.case_timeline=QListWidget();tl.addWidget(self.case_timeline)
        tabs.addTab(timeline,"Case Timeline")

        notes=QWidget();nl=QVBoxLayout(notes)
        self.case_notes=QTextEdit();nl.addWidget(self.case_notes)
        save=QPushButton("Save Case Notes");save.clicked.connect(self.save_case_notes);nl.addWidget(save)
        tabs.addTab(notes,"Investigation Notes")

        l.addWidget(tabs,1)
        return w

    def tags(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(28,25,28,25)
        l.addWidget(QLabel("Tag Intelligence",objectName="pageTitle"))
        self.tagtable=QTableWidget(0,2);self.tagtable.setHorizontalHeaderLabels(["Tag","Documents"])
        self.tagtable.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);l.addWidget(self.tagtable,1)
        return w

    def cases(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(28,25,28,25)
        l.addWidget(QLabel("Cases & Collections",objectName="pageTitle"))
        self.casetable=QTableWidget(0,3);self.casetable.setHorizontalHeaderLabels(["Case","Description","Documents"])
        self.casetable.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.casetable.itemDoubleClicked.connect(lambda _:self.open_selected_case())
        l.addWidget(self.casetable,1)
        return w

    def settings(self):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(28,25,28,25)
        l.addWidget(QLabel("Settings & Maintenance",objectName="pageTitle"))
        p=QFrame(objectName="panel");pl=QVBoxLayout(p)
        pl.addWidget(QLabel("LOCAL DATABASE",objectName="sectionTitle"))
        pl.addWidget(QLabel(str(self.db.path)))
        b=QPushButton("Create Database Backup");b.clicked.connect(self.backup);pl.addWidget(b)
        r=QPushButton("Rebuild Search Index");r.clicked.connect(self.rebuild);pl.addWidget(r)
        o=QPushButton("Check Optional OCR");o.clicked.connect(self.check_ocr);pl.addWidget(o)
        l.addWidget(p);l.addStretch();return w

    def page(self,row):
        self.pages.setCurrentIndex(row)
        if row==0:self.refresh_dashboard()
        elif row==1:self.refresh_library()
        elif row==2:self.refresh_queue(self.review_table,True)
        elif row==3:self.refresh_queue(self.favorite_table,False)
        elif row==4:self.refresh_duplicates()
        elif row==5:self.refresh_health()
        elif row==6:self.refresh_investigation()
        elif row==7:self.refresh_tags()
        elif row==8:self.refresh_cases()

    def refresh_all(self):
        self.refresh_dashboard();self.refresh_category_list();self.set_filter("All");self.refresh_health();self.refresh_cases();self.refresh_investigation()

    def refresh_dashboard(self):
        s=self.service.stats()
        for k,v in s.items():self.kpis[k].setText(self.human(v) if k=="storage" else f"{v:,}")
        lines=[]
        if s["review"]:lines.append(f"• {s['review']:,} documents await review")
        if s["duplicates"]:lines.append(f"• {s['duplicates']:,} documents are in duplicate groups")
        if s["missing"]:lines.append(f"• {s['missing']:,} indexed files are missing")
        self.signals.setText("\n".join(lines) if lines else "✓ No immediate archive problems.")
        self.recent.clear()
        for r in self.service.recent():
            it=QListWidgetItem(f"{r['title'] or r['name']}  ·  {r['category']}")
            it.setData(Qt.UserRole,r["id"]);self.recent.addItem(it)

    def refresh_library(self):
        rows=self.service.documents(self.search.text(),self.current_filter,self.current_category)
        self.table.setRowCount(0)
        for r in rows:
            i=self.table.rowCount();self.table.insertRow(i)
            vals=[r["title"] or r["name"],r["category"],r["extension"].replace(".","").upper(),self.human(r["size"]),self.date(r["modified_at"]),r["importance"],"REVIEW" if r["needs_review"] else "OK",("MISSING" if r["missing"] else (r["scan_status"] if "scan_status" in r.keys() else "READY"))]
            for c,v in enumerate(vals):self.table.setItem(i,c,QTableWidgetItem(str(v)))
            self.table.item(i,0).setData(Qt.UserRole,r["id"])
        self.libcount.setText(f"{len(rows):,} results")

    def refresh_queue(self,t,review):
        rows=self.service.documents("", "Review" if review else "Favorites");t.setRowCount(0)
        for r in rows:
            i=t.rowCount();t.insertRow(i)
            vals=[r["title"] or r["name"],r["category"],r["extension"].replace(".","").upper(),self.human(r["size"]),"MISSING" if r["missing"] else "READY"]
            for c,v in enumerate(vals):t.setItem(i,c,QTableWidgetItem(str(v)))
            t.item(i,0).setData(Qt.UserRole,r["id"])
        (self.review_label if review else self.favorite_label).setText(f"{len(rows):,} documents")

    def refresh_duplicates(self):
        rows=self.service.duplicate_groups();self.duptable.setRowCount(0);wasted=0
        for r in rows:
            reclaim=r["total_size"]*(r["count"]-1)/r["count"];wasted+=reclaim
            i=self.duptable.rowCount();self.duptable.insertRow(i)
            for c,v in enumerate([r["sha256"],r["count"],self.human(reclaim),r["names"]]):self.duptable.setItem(i,c,QTableWidgetItem(str(v)))
        self.dupsummary.setText(f"{len(rows):,} duplicate groups • estimated reclaimable space: {self.human(wasted)}")

    def refresh_health(self):
        while self.healthgrid.count():
            item=self.healthgrid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        s=self.service.stats();total=max(1,s["documents"])
        metrics=[
            ("Archive coverage",100-s["missing"]*100/total,"Missing-file risk"),
            ("Review completion",100-s["review"]*100/total,"Human review progress"),
            ("Duplicate cleanliness",100-s["duplicates"]*100/total,"Exact duplicate pressure")
        ]
        for i,(name,pct,tip) in enumerate(metrics):
            f=QFrame(objectName="healthcard");fl=QVBoxLayout(f);fl.addWidget(QLabel(name,objectName="sectionTitle"))
            fl.addWidget(QLabel(f"{max(0,pct):.0f}%",objectName="healthvalue"));fl.addWidget(QLabel(tip))
            self.healthgrid.addWidget(f,i,0)

    def refresh_tags(self):
        rows=self.db.query("""SELECT t.name,COUNT(dt.document_id) n FROM tags t
        LEFT JOIN document_tags dt ON dt.tag_id=t.id GROUP BY t.id ORDER BY n DESC,t.name""")
        self.tagtable.setRowCount(0)
        for r in rows:
            i=self.tagtable.rowCount();self.tagtable.insertRow(i);self.tagtable.setItem(i,0,QTableWidgetItem(r["name"]));self.tagtable.setItem(i,1,QTableWidgetItem(str(r["n"])))

    def refresh_cases(self):
        rows=self.service.collections();self.casetable.setRowCount(0)
        for r in rows:
            i=self.casetable.rowCount();self.casetable.insertRow(i)
            for c,v in enumerate([r["name"],r["description"],str(r["n"])]):self.casetable.setItem(i,c,QTableWidgetItem(v))
        self.case_combo.blockSignals(True)
        current=self.case_combo.currentData()
        self.case_combo.clear()
        self.case_combo.addItem("— Select a case —",None)
        for r in rows:self.case_combo.addItem(r["name"],r["id"])
        if current:
            idx=self.case_combo.findData(current)
            if idx>=0:self.case_combo.setCurrentIndex(idx)
        self.case_combo.blockSignals(False)

    def refresh_investigation(self):
        if self.current_case_id:self.load_case(self.case_combo.findData(self.current_case_id))

    def load_case(self,index):
        case_id=self.case_combo.itemData(index)
        self.current_case_id=case_id
        if not case_id:
            self.case_summary.setText("Select a case to load its evidence.")
            return
        case=self.db.one("SELECT * FROM collections WHERE id=?",(case_id,))
        docs=self.investigation.case_documents(case_id)
        count,size,cats=self.investigation.case_stats(case_id)
        self.case_summary.setText(f"<b>{case['name']}</b>  •  {count} evidence documents  •  {self.human(size)}  •  "+", ".join(f"{k}: {v}" for k,v in cats.items()))
        self.board.set_documents(docs,self.investigation)
        self.left_doc.clear();self.right_doc.clear()
        for d in docs:
            label=d["title"] or d["name"];self.left_doc.addItem(label,d["id"]);self.right_doc.addItem(label,d["id"])
        self.case_notes.setPlainText(case["description"] or "")
        self.case_timeline.clear()
        for r in self.investigation.timeline([d["id"] for d in docs]):
            self.case_timeline.addItem(f"{r['value']}  —  {r['title'] or r['name']}")
        self.run_conflicts()

    def compare_docs(self):
        a=self.left_doc.currentData();b=self.right_doc.currentData()
        if not a or not b or a==b:return
        da=self.service.get(a);db=self.service.get(b)
        self.compare_left.setPlainText(da["text"] or "No extracted text.")
        self.compare_right.setPlainText(db["text"] or "No extracted text.")

    def run_conflicts(self):
        if not self.current_case_id:return
        ids=[d["id"] for d in self.investigation.case_documents(self.current_case_id)]
        conflicts=self.investigation.conflicts(ids)
        self.conflict_table.setRowCount(0)
        for typ,values in conflicts:
            i=self.conflict_table.rowCount();self.conflict_table.insertRow(i)
            self.conflict_table.setItem(i,0,QTableWidgetItem(typ.upper()))
            self.conflict_table.setItem(i,1,QTableWidgetItem("  VS  ".join(v for v,_ in values)))
            names=[]
            for value,docids in values:
                for did in docids:
                    d=self.service.get(did);names.append(f"{d['title'] or d['name']} → {value}")
            self.conflict_table.setItem(i,2,QTableWidgetItem(" | ".join(names)))

    def save_case_notes(self):
        if self.current_case_id:
            self.db.execute("UPDATE collections SET description=? WHERE id=?",(self.case_notes.toPlainText(),self.current_case_id))
            self.statusBar().showMessage("Investigation notes saved")

    def new_case(self):
        name,ok=QInputDialog.getText(self,"New Investigation","Case name:")
        if ok and name:
            self.service.create_collection(name,"Investigation created in JASS Document Detective")
            self.refresh_cases()
            idx=self.case_combo.findText(name)
            if idx>=0:self.case_combo.setCurrentIndex(idx)
            self.nav.setCurrentRow(6)

    def open_selected_case(self):
        row=self.casetable.currentRow()
        if row<0:return
        name=self.casetable.item(row,0).text()
        idx=self.case_combo.findText(name)
        if idx>=0:self.case_combo.setCurrentIndex(idx)
        self.nav.setCurrentRow(6)

    def inspect_selected(self):
        items=self.table.selectedItems()
        if items:self.inspect(items[0].data(Qt.UserRole))

    def inspect_from(self,t):
        items=t.selectedItems()
        if items:self.inspect(items[0].data(Qt.UserRole))

    def inspect(self,doc_id):
        r=self.service.get(doc_id)
        if not r:return
        dlg=QDialog(self);dlg.setWindowTitle("Document Detective — Inspector");dlg.resize(1150,820)
        l=QVBoxLayout(dlg);l.addWidget(QLabel(r["title"] or r["name"],objectName="dialogTitle"));l.addWidget(QLabel(r["path"],objectName="muted"))
        tabs=QTabWidget();l.addWidget(tabs,1)

        info=QWidget();il=QVBoxLayout(info);form=QFormLayout()
        for label,value in [("Category",r["category"]),("Type",r["mime_type"] or r["extension"]),("Size",self.human(r["size"])),("SHA-256",r["sha256"] or "—"),("Pages",str(r["page_count"] or "—")),("Status","Needs review" if r["needs_review"] else "Reviewed")]:
            form.addRow(label+":",QLabel(value))
        il.addLayout(form)
        actions=QHBoxLayout()
        for text,slot in [
            ("✓ Mark Reviewed",lambda:self.service.reviewed(doc_id)),
            ("★ Favorite",lambda:self.service.toggle(doc_id,"is_favorite")),
            ("🏷 Add Tag",lambda:self.tag(doc_id)),
            ("Open",lambda:self.open_file(doc_id)),
            ("Reveal",lambda:self.reveal(doc_id))
        ]:
            q=QPushButton(text);q.clicked.connect(slot);actions.addWidget(q)
        il.addLayout(actions)
        ocr=QPushButton("Run Optional OCR on This File");ocr.clicked.connect(lambda:self.ocr_document(doc_id,dlg));il.addWidget(ocr)
        tabs.addTab(info,"Overview")
        tabs.addTab(self.preview_widget(r),"Preview")
        tx=QTextEdit();tx.setReadOnly(True);tx.setPlainText(r["text"] or "No extracted text.");tabs.addTab(tx,"Extracted Text")
        cl=QTextEdit();cl.setReadOnly(True);cl.setPlainText("\n".join(f"{x['clue_type'].upper():10} {x['value']}" for x in self.service.clues(doc_id)) or "No clues detected.");tabs.addTab(cl,"Entities & Clues")
        rel=QWidget();rl=QVBoxLayout(rel);rt=QTableWidget(0,3);rt.setHorizontalHeaderLabels(["Related Document","Relationship","Category"]);rt.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);rl.addWidget(rt)
        for rr in self.service.related(doc_id):
            score,d,common=rr;i=rt.rowCount();rt.insertRow(i)
            for c,v in enumerate([d["title"] or d["name"],f"{score} shared clue(s)",""+d["category"]]):rt.setItem(i,c,QTableWidgetItem(v))
        tabs.addTab(rel,"Related")
        close=QDialogButtonBox(QDialogButtonBox.Close);close.rejected.connect(dlg.reject);l.addWidget(close)
        dlg.exec();self.refresh_all()

    def ocr_document(self,doc_id,dlg):
        r=self.service.get(doc_id)
        if not r:return
        text,error=self.investigation.run_ocr(r["path"])
        if error:
            QMessageBox.information(dlg,"OCR",error+"\n\nInstall Tesseract and add it to PATH to enable OCR.")
            return
        self.investigation.append_ocr_text(doc_id,text)
        QMessageBox.information(dlg,"OCR complete",f"Added {len(text):,} characters to the searchable document text.")
        dlg.accept()

    def preview_widget(self,r):
        w=QWidget();l=QVBoxLayout(w);ext=r["extension"].lower()
        if ext==".pdf":
            controls=QHBoxLayout();prev=QPushButton("‹");nxt=QPushButton("›");page=QSpinBox();page.setRange(1,max(1,r["page_count"]));page.setValue(1)
            controls.addWidget(prev);controls.addWidget(page);controls.addWidget(nxt);controls.addStretch();l.addLayout(controls)
            view=QScrollArea();view.setWidgetResizable(True);image=QLabel(alignment=Qt.AlignCenter);view.setWidget(image);l.addWidget(view,1)
            def show():
                try:
                    data=render_pdf_page(r["path"],page.value()-1,1.35);pix=QPixmap();pix.loadFromData(data);image.setPixmap(pix)
                except Exception as e:image.setText(f"PDF preview unavailable:\n{e}")
            prev.clicked.connect(lambda:(page.setValue(max(1,page.value()-1)),show()));nxt.clicked.connect(lambda:(page.setValue(min(page.maximum(),page.value()+1)),show()));page.valueChanged.connect(lambda _:show());show()
        elif ext in IMAGE_EXTENSIONS:
            view=QScrollArea();view.setWidgetResizable(True);image=QLabel(alignment=Qt.AlignCenter);pix=QPixmap(r["path"]);image.setPixmap(pix.scaled(1050,680,Qt.KeepAspectRatio,Qt.SmoothTransformation));view.setWidget(image);l.addWidget(view)
        else:l.addWidget(QLabel("Use the Extracted Text tab for this document type."))
        return w

    def tag(self,id):
        tag,ok=QInputDialog.getText(self,"Add Tag","Tag name:")
        if ok and tag:self.service.add_tag(id,tag)

    def open_file(self,id):
        r=self.service.get(id)
        if r:
            self.db.execute("UPDATE documents SET last_opened=? WHERE id=?",(time.time(),id))
            self.db.execute("INSERT INTO activity(document_id,action,detail) VALUES(?,?,?)",(id,"opened",r["path"]))
            QDesktopServices.openUrl(QUrl.fromLocalFile(r["path"]))

    def reveal(self,id):
        r=self.service.get(id)
        if not r:return
        p=Path(r["path"])
        if sys.platform.startswith("win"):subprocess.Popen(["explorer.exe","/select,",str(p)])
        else:QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Add folder to Detective")
        if folder:self.start_scan(folder)

    def scan_again(self):
        rows=self.db.query("SELECT path FROM folders")
        if rows:self.start_scan(rows[0]["path"])
        else:self.add_folder()

    def start_scan(self,folder):
        folder = str(Path(folder).expanduser().resolve())
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Scan in progress", "A document scan is already running.")
            return

        self.statusBar().showMessage(f"Starting scan • {folder}")
        self.worker = Worker(self.db.path, folder)
        self.worker.progress.connect(
            lambda i, n, name: self.statusBar().showMessage(
                f"Indexing {i:,}/{n:,} • {name}" if n else "No supported documents found"
            )
        )
        self.worker.done.connect(self.scan_finished)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.scan_thread_finished)
        self.worker.start()

    def scan_finished(self, result):
        # The worker has committed its changes before this signal is emitted.
        self.refresh_all()

        discovered = result.get("discovered", 0)
        indexed = result.get("indexed", 0)
        unchanged = result.get("unchanged", 0)
        failed = result.get("failed", 0)

        self.statusBar().showMessage(
            f"Scan complete • {discovered:,} found • "
            f"{indexed:,} indexed • {unchanged:,} unchanged • "
            f"{failed:,} failed"
        )

        if failed:
            QMessageBox.warning(
                self,
                "Scan completed with warnings",
                f"Found: {discovered:,}\n"
                f"Indexed: {indexed:,}\n"
                f"Unchanged: {unchanged:,}\n"
                f"Extraction/scan failures: {failed:,}\n\n"
                "Failed files remain in the Library. "
                "Their errors have been recorded."
            )
        else:
            QMessageBox.information(
                self,
                "Scan complete",
                f"Found: {discovered:,}\n"
                f"Indexed: {indexed:,}\n"
                f"Unchanged: {unchanged:,}"
            )

    def scan_failed(self, message):
        self.statusBar().showMessage("Scan failed")
        QMessageBox.critical(
            self,
            "Document Scan Failed",
            "The scan could not be completed.\n\n" + message,
        )

    def scan_thread_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()

    def set_filter(self,name):
        self.current_filter=name
        if hasattr(self,"filters"):
            for k,b in self.filters.items():b.setChecked(k==name)
        self.refresh_library()

    def set_category(self,index):
        self.current_category="All" if index==0 else self.category.itemText(index)
        self.refresh_library()

    def refresh_category_list(self):
        self.category.blockSignals(True);current=self.current_category
        self.category.clear();self.category.addItem("All")
        for r in self.service.categories():self.category.addItem(r["category"])
        idx=self.category.findText(current)
        self.category.setCurrentIndex(idx if idx>=0 else 0)
        self.category.blockSignals(False)

    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,"Database Backup","document_detective_backup.db","SQLite Database (*.db)")
        if path:self.service.backup(path);QMessageBox.information(self,"Backup","Database backup created.")

    def rebuild(self):
        self.db.rebuild_fts();QMessageBox.information(self,"Search","FTS5 index rebuilt successfully.")

    def check_ocr(self):
        text,error=self.investigation.run_ocr(__file__)
        if "not found" in error.lower():QMessageBox.information(self,"Optional OCR","Tesseract is not installed or not on PATH.")
        else:QMessageBox.information(self,"Optional OCR","Tesseract is available.")

    def export_index(self):
        path,_=QFileDialog.getSaveFileName(self,"Export Index","","CSV (*.csv);;JSON (*.json)")
        if path:
            self.service.export_json(path) if path.lower().endswith(".json") else self.service.export_csv(path)
            QMessageBox.information(self,"Export","Index exported.")

    def new_case_from_any(self):self.new_case()

    def human(self,n):
        n=float(n or 0)
        for u in ["B","KB","MB","GB","TB"]:
            if n<1024:return f"{n:.1f} {u}"
            n/=1024
        return f"{n:.1f} PB"

    def date(self,v):
        from datetime import datetime
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M") if v else "—"

    def style(self):
        self.setStyleSheet("""
        QWidget{font-family:'Segoe UI';font-size:13px;color:#172033;}
        QMainWindow{background:#f4f7fb;}
        #topbar{background:#0c1625;border-bottom:1px solid #26364d;}
        #brand{color:#fff;font-size:18px;font-weight:800;letter-spacing:1px;}
        #badge{color:#a7f3d0;background:#12342d;border:1px solid #17624f;border-radius:12px;padding:5px 10px;margin-left:10px;font-size:10px;font-weight:800;}
        #topbar QLineEdit{background:#1b293d;color:#fff;border:1px solid #34465e;border-radius:9px;padding:10px 13px;}
        QPushButton{background:#fff;border:1px solid #d7dee8;border-radius:8px;padding:8px 13px;}
        QPushButton:hover{background:#eef5ff;border-color:#9ab9e8;}
        QPushButton:checked{background:#e7f0ff;border-color:#4d8de7;color:#185abd;font-weight:700;}
        #sidebar{background:#101a2b;}
        #navtitle{color:#71829b;font-size:10px;font-weight:800;letter-spacing:1.4px;padding:4px 9px;}
        QListWidget{background:transparent;border:0;color:#c8d2e0;}
        QListWidget::item{padding:12px 10px;border-radius:8px;margin:2px 0;}
        QListWidget::item:selected{background:#263955;color:#fff;}
        #pageTitle{font-size:29px;font-weight:800;color:#111b2d;}
        #subtitle,#muted{color:#6b778c;}
        #kpi,#panel,#healthcard{background:#fff;border:1px solid #e1e7ef;border-radius:13px;}
        #kpi{padding:8px;}
        #kpiLabel{color:#6b778c;font-size:11px;font-weight:800;letter-spacing:.8px;}
        #kpiValue{font-size:27px;font-weight:800;color:#111b2d;}
        #kpiTip{color:#8994a6;font-size:11px;}
        #panel,#healthcard{padding:8px;}
        #sectionTitle{font-size:11px;font-weight:800;letter-spacing:1px;color:#66758a;}
        #healthvalue{font-size:32px;font-weight:800;color:#185abd;}
        QTableWidget{background:#fff;border:1px solid #e1e7ef;border-radius:10px;gridline-color:#eef1f5;alternate-background-color:#f8fafc;}
        QHeaderView::section{background:#f1f4f8;color:#526075;border:0;border-bottom:1px solid #dce3ec;padding:9px;font-weight:700;}
        QTableWidget::item{padding:6px;}
        QTableWidget::item:selected{background:#dceaff;color:#102a43;}
        QDialog{background:#f6f8fb;}
        #dialogTitle{font-size:22px;font-weight:800;color:#111b2d;}
        QTabWidget::pane{border:1px solid #dfe5ed;background:#fff;border-radius:8px;}
        QTabBar::tab{padding:9px 14px;background:#edf1f6;border:0;margin-right:2px;}
        QTabBar::tab:selected{background:#fff;color:#185abd;font-weight:700;}
        QTextEdit{background:#fff;border:1px solid #d8e0ea;border-radius:8px;padding:8px;}
        QComboBox,QSpinBox{background:#fff;border:1px solid #d8e0ea;border-radius:7px;padding:7px;}
        """)


class EvidenceBoard(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene=QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(self.renderHints())
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.docs=[]

    def set_documents(self,docs,investigation):
        self.docs=docs
        self.scene.clear()
        if not docs:
            self.scene.addText("No evidence in this case yet.")
            return
        positions={}
        cols=3
        for idx,d in enumerate(docs):
            x=(idx%cols)*290
            y=(idx//cols)*145
            positions[d["id"]]=(x,y)
            card=QGraphicsRectItem(QRectF(x,y,255,112))
            card.setBrush(QBrush(QColor("#ffffff")))
            card.setPen(QPen(QColor("#cbd5e1")))
            self.scene.addItem(card)
            title=QGraphicsTextItem((d["title"] or d["name"])[:32])
            title.setDefaultTextColor(QColor("#172033"));title.setFont(QFont("Segoe UI",10,QFont.Bold));title.setPos(x+12,y+10);self.scene.addItem(title)
            meta=QGraphicsTextItem(f"{d['category']}\n{d['extension'].upper()}  •  {self._size(d['size'])}")
            meta.setDefaultTextColor(QColor("#667085"));meta.setPos(x+12,y+40);self.scene.addItem(meta)
        # Relationship lines for explicitly related evidence.
        pen=QPen(QColor("#7c8da6"),2)
        for d in docs:
            for rel in investigation.relations(d["id"]):
                if rel["related_id"] in positions and d["id"] < rel["related_id"]:
                    x1,y1=positions[d["id"]];x2,y2=positions[rel["related_id"]]
                    self.scene.addLine(x1+255,y1+55,x2,y2+55,pen)

    def _size(self,n):
        n=float(n or 0)
        for u in ["B","KB","MB","GB"]:
            if n<1024:return f"{n:.1f}{u}"
            n/=1024
        return f"{n:.1f}TB"


if __name__=="__main__":
    app=QApplication(sys.argv)
    w=MainWindow();w.show()
    sys.exit(app.exec())
