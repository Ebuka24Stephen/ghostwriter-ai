import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.environ.get("GHOSTWRITER_PROVIDER", "gemini")
GROQ_API_KEY = "GROQ_API_KEY"
GEMINI_API_KEY = "GEMINI_API_KEY"
LLM_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
KEEP_RATIO = float(os.environ.get("GHOSTWRITER_KEEP_RATIO", "0.4"))
REWRITE_CHUNK_SIZE = int(os.environ.get("GHOSTWRITER_CHUNK_SIZE", "8"))
REWRITE_TEMPERATURE = float(os.environ.get("GHOSTWRITER_TEMPERATURE", "0.8"))
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
STYLE_PROMPT_FILE = Path("data/style_prompt.txt")
INPUT_FILE = Path("data/input/report.txt")
OUTPUT_FILE = Path("data/rewritten/report_rewritten.txt")
VECTOR_DB_DIR = Path("data/vector_db")
COLLECTION_NAME = "ghostwriter"