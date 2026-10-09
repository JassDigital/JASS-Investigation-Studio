import re
from pathlib import Path

CATEGORY_RULES={
    "Land & Property":["jamabandi","khewat","khatoni","land record","registry","mutation","property","sale deed"],
    "Tax & Finance":["income tax","itr","tax return","pension","salary slip","bank statement","form 16","invoice","receipt"],
    "Medical":["medical","hospital","prescription","health","diagnostic","lab report","medicine"],
    "Identity":["passport","aadhaar","pan card","driving licence","identity","id card"],
    "Legal":["court","case","affidavit","agreement","legal","notice","petition"],
    "Insurance":["insurance","policy","premium","claim"],
    "Education":["certificate","degree","marksheet","school","university","college"],
    "Correspondence":["letter","application","notice","email","correspondence"],
}

def infer_category(path,text):
    s=(path.name+" "+text[:10000]).lower()
    for category,words in CATEGORY_RULES.items():
        if any(w in s for w in words):
            return category
    return "Images & Photos" if path.suffix.lower() in {".jpg",".jpeg",".png",".bmp",".gif",".tif",".tiff",".webp"} else "General"

def extract_clues(text):
    if not text:return []
    out=[]
    patterns=[
        ("date",r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"),
        ("year",r"\b(?:19|20)\d{2}\b"),
        ("reference",r"\b(?:Khewat|Khatauni|Khatoni|Mutation|Registry|File|Case|Ref(?:erence)?)\s*(?:No\.?|Number)?\s*[:#-]?\s*[A-Za-z0-9/-]{1,40}"),
        ("amount",r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d{1,2})?"),
    ]
    for typ,pat in patterns:
        for value in dict.fromkeys(re.findall(pat,text,re.I)):
            out.append((typ,value.strip()))
    # Conservative name-like phrases. This is a hint, not identity recognition.
    names=re.findall(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b",text)
    stop={"Document Detective","Jass Digital","Microsoft Office","Windows Server","Income Tax","Land Records"}
    for value in dict.fromkeys(names):
        if value not in stop: out.append(("name",value))
    places=re.findall(r"\b(?:Village|District|City|Town|Tehsil|Block)\s*[:\-]?\s*[A-Z][A-Za-z -]{2,40}",text,re.I)
    for value in dict.fromkeys(places): out.append(("place",value.strip()))
    return out[:200]

def timeline_events(text):
    if not text:return []
    years=sorted(set(re.findall(r"\b(?:19|20)\d{2}\b",text)))
    return [(y,"Mentioned in document") for y in years]

def clue_values(db,doc_id):
    return db.query("SELECT clue_type,value FROM clues WHERE document_id=? ORDER BY clue_type,value",(doc_id,))
