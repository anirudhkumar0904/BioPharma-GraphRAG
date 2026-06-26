"""
Centralized configuration for BioPharma GraphRAG.
Loads from .env file or environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
GRAPH_PATH = DATA_DIR / "graph.gpickle"

# Create dirs if they don't exist
for d in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── LLM ──
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")  # cheaper, works great
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")

# ── Embeddings ──
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ── ChromaDB ──
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma_db"))

# ── Neo4j (optional) ──
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
USE_NEO4J = bool(NEO4J_URI)

# ── Entity Types ──
ENTITY_TYPES = ["DRUG", "DISEASE", "GENE", "PROTEIN", "PATHWAY", "SIDE_EFFECT"]
RELATION_TYPES = [
    "TARGETS", "TREATS", "CAUSES", "ASSOCIATED_WITH",
    "INTERACTS_WITH", "UPREGULATES", "DOWNREGULATES",
    "INHIBITS", "ACTIVATES", "BIOMARKER_FOR",
    "SIDE_EFFECT_OF", "METABOLIZED_BY", "PART_OF_PATHWAY"
]
