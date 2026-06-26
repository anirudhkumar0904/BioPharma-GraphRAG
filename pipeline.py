"""
pipeline.py — End-to-end pipeline: fetch data → extract entities → build graph → index vectors.

Run this once to set up everything, then use the Streamlit app to query.
"""
import json
import time
from tqdm import tqdm
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR

from data_fetcher import fetch_all_data
from entity_extractor import (
    extract_entities_from_text,
    extract_from_structured_data,
    merge_extractions
)
from graph_builder import build_graph, save_graph
from vector_store import BioVectorStore


def run_pipeline(skip_fetch: bool = False, skip_llm_extraction: bool = False):
    """
    Full pipeline:
      1. Fetch data from PubMed + Open Targets
      2. Extract entities (LLM for text, direct for structured data)
      3. Build knowledge graph
      4. Index into vector store
    """
    print("=" * 60)
    print("  BioPharma GraphRAG — Full Pipeline")
    print("=" * 60)

    # ── Step 1: Fetch Data ──
    data_path = RAW_DATA_DIR / "biomedical_data.json"

    if skip_fetch and data_path.exists():
        print("\n📂 Loading existing data...")
        with open(data_path) as f:
            raw_data = json.load(f)
    else:
        print("\n🌐 Step 1: Fetching biomedical data...")
        raw_data = fetch_all_data()

    articles = raw_data.get("pubmed_articles", [])
    gene_assocs = raw_data.get("gene_associations", [])
    drug_assocs = raw_data.get("drug_associations", [])

    print(f"\n   Data loaded:")
    print(f"   - {len(articles)} PubMed articles")
    print(f"   - {len(gene_assocs)} gene-disease associations")
    print(f"   - {len(drug_assocs)} drug-disease associations")

    # ── Step 2: Extract Entities ──
    print("\n🔬 Step 2: Extracting entities and relationships...")
    all_extractions = []

    # 2a. Structured data (no LLM needed — already structured!)
    print("  Processing structured data (Open Targets)...")
    structured = extract_from_structured_data(gene_assocs, drug_assocs)
    all_extractions.append(structured)
    print(f"   → {len(structured['entities'])} entities, {len(structured['relationships'])} relationships")

    # 2b. LLM extraction from PubMed abstracts (optional, costs API tokens)
    if not skip_llm_extraction:
        print("  Extracting from PubMed abstracts (LLM)...")
        for article in tqdm(articles[:100], desc="LLM extraction"):  # limit for cost
            text = f"{article.get('title', '')}. {article.get('abstract', '')}"
            extraction = extract_entities_from_text(text, source_id=article.get("pmid", ""))
            all_extractions.append(extraction)
            time.sleep(0.3)  # rate limit
    else:
        print("  ⏩ Skipping LLM extraction (using structured data only)")

    # ── Step 3: Merge & Build Graph ──
    print("\n🏗️  Step 3: Building knowledge graph...")
    merged = merge_extractions(all_extractions)
    print(f"   Merged: {len(merged['entities'])} entities, {len(merged['relationships'])} relationships")

    # Save merged data
    merged_path = PROCESSED_DATA_DIR / "merged_extractions.json"
    with open(merged_path, "w") as f:
        json.dump(merged, f, indent=2, default=str)

    G = build_graph(merged)
    save_graph(G)

    # ── Step 4: Index Vector Store ──
    print("\n📦 Step 4: Indexing vector store...")
    vs = BioVectorStore()
    vs.index_articles(articles)
    vs.index_graph_relations(merged["relationships"])

    stats = vs.get_stats()
    print(f"   Vector store: {stats['text_chunks']} text chunks, {stats['graph_relations']} graph relations")

    # ── Done ──
    print("\n" + "=" * 60)
    print("  ✅ Pipeline complete! Run the Streamlit app:")
    print("     streamlit run app.py")
    print("=" * 60)

    return G, vs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BioPharma GraphRAG Pipeline")
    parser.add_argument("--skip-fetch", action="store_true", help="Use existing data")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM extraction (use structured only)")
    args = parser.parse_args()

    run_pipeline(skip_fetch=args.skip_fetch, skip_llm_extraction=args.skip_llm)
