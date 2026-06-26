# 🧬 BioPharma GraphRAG

> A Graph-based Retrieval Augmented Generation system for exploring Drug-Disease-Gene interactions and discovering drug repurposing opportunities.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## What It Does

Ask natural language questions about biomedical relationships and get **evidence-backed answers** with multi-hop reasoning through a knowledge graph:

- **"What genes connect diabetes and Alzheimer's?"** → Traverses the graph to find shared genetic links
- **"What other diseases could Metformin treat?"** → Follows Drug → Gene → Disease paths for repurposing candidates
- **"How does APOE relate to neurodegeneration?"** → Explores the entity neighborhood with evidence chains

Every answer includes a **hallucination score** — claims are verified against the source data.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Query                            │
│         "What genes connect diabetes & Alzheimer's?"     │
└──────────────────────┬──────────────────────────────────┘
                       ▼
              ┌─────────────────┐
              │ Query Classifier │  → shared_genes / drug_repurposing /
              │                 │     explore / mechanism / general
              └────────┬────────┘
                       ▼
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌───────────────┐            ┌────────────────┐
│ Graph Traversal│            │  Vector Search  │
│  (NetworkX)   │            │   (ChromaDB)    │
│               │            │                 │
│ • Multi-hop   │            │ • PubMed chunks │
│ • Shared genes│            │ • Graph text    │
│ • Drug paths  │            │ • Semantic sim  │
└───────┬───────┘            └────────┬────────┘
        └──────────────┬──────────────┘
                       ▼
              ┌─────────────────┐
              │  Answer Generator│  (GPT-4o-mini / Ollama)
              │  + Hallucination │
              │    Detector      │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │  Streamlit UI   │
              │  + Graph Viz    │
              └─────────────────┘
```

## Data Sources (All Free)

| Source | What It Provides | Access |
|--------|-----------------|--------|
| **PubMed** (NCBI) | Research abstracts | Free API, no key needed |
| **Open Targets** | Drug-gene-disease associations | Free GraphQL API |

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/biopharma-graphrag.git
cd biopharma-graphrag
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env → add your OpenAI API key
```

**Free alternative:** Use Ollama for local LLM (no API key needed):
```bash
# Install Ollama: https://ollama.ai
ollama pull llama3
# Then set in .env:
# OLLAMA_BASE_URL=http://localhost:11434
# LLM_MODEL=llama3
```

### 3. Run Pipeline (One-Time Setup)

```bash
# Full pipeline (fetches data + LLM extraction) — takes ~15 min
python pipeline.py

# Faster: skip LLM extraction, use only structured data
python pipeline.py --skip-llm

# Even faster: reuse previously fetched data
python pipeline.py --skip-fetch --skip-llm
```

### 4. Launch App

```bash
streamlit run app.py
```

Open `http://localhost:8501` and start querying!

## Project Structure

```
biopharma-graphrag/
├── app.py                 # Streamlit UI (main entry point)
├── config.py              # Centralized configuration
├── data_fetcher.py        # Pulls data from PubMed + Open Targets
├── entity_extractor.py    # LLM-based entity/relationship extraction
├── graph_builder.py       # Builds NetworkX knowledge graph
├── vector_store.py        # ChromaDB vector store for text chunks
├── hybrid_retriever.py    # Combines graph + vector retrieval
├── answer_generator.py    # LLM answer generation + hallucination check
├── graph_viz.py           # Interactive graph visualization (PyVis)
├── pipeline.py            # End-to-end build pipeline
├── requirements.txt       # Dependencies
├── .env.example           # Config template
└── data/
    ├── raw/               # Fetched PubMed + Open Targets data
    ├── processed/         # Merged extractions
    ├── graph.gpickle      # Serialized knowledge graph
    └── chroma_db/         # Vector store persistence
```

## Google Colab Setup

```python
# Cell 1: Install dependencies
!pip install streamlit networkx pyvis openai sentence-transformers chromadb biopython pydantic python-dotenv tqdm lxml

# Cell 2: Clone the repo
!git clone https://github.com/yourusername/biopharma-graphrag.git
%cd biopharma-graphrag

# Cell 3: Set API key
import os
os.environ["OPENAI_API_KEY"] = "your-key-here"

# Cell 4: Run pipeline (structured data only — free, no LLM cost)
!python pipeline.py --skip-llm

# Cell 5: Launch Streamlit
!pip install pyngrok
from pyngrok import ngrok
ngrok.set_auth_token("your-ngrok-token")
public_url = ngrok.connect(8501)
print(f"App URL: {public_url}")
!streamlit run app.py --server.port 8501
```

## Deployment

### Streamlit Cloud (Free)
1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo → deploy

### Hugging Face Spaces (Free)
1. Create a new Space (Streamlit SDK)
2. Upload all files
3. Add `OPENAI_API_KEY` to Space secrets

## Key Features

- **Multi-hop reasoning** — traverse Drug → Gene → Disease paths
- **Shared gene discovery** — find hidden genetic links between diseases
- **Drug repurposing** — identify new therapeutic opportunities
- **Hallucination detection** — every claim verified with trust scores
- **Interactive graph visualization** — explore the knowledge graph visually
- **Hybrid retrieval** — combines graph structure with semantic search

## License

MIT
