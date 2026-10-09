from pathlib import Path

APP_NAME = "JASS Document Detective"
APP_VERSION = "1.3.2 Reliable Investigation Studio"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "document_detective.db"

SUPPORTED = {
    ".pdf",".txt",".md",".markdown",".csv",".html",".htm",
    ".docx",".xlsx",".xlsm",".pptx",
    ".jpg",".jpeg",".png",".bmp",".gif",".tif",".tiff",".webp"
}
IMAGE_EXTENSIONS = {".jpg",".jpeg",".png",".bmp",".gif",".tif",".tiff",".webp"}
OFFICE_EXTENSIONS = {".docx",".xlsx",".xlsm",".pptx"}
TEXT_EXTENSIONS = {".txt",".md",".markdown",".csv",".html",".htm"}
