"""
ingest_graph.py — Populate BioPharma Knowledge Graph & Vector Relations
"""
import json
import networkx as nx
from pathlib import Path

from config import PROCESSED_DATA_DIR
from graph_builder import build_graph, save_graph
from vector_store import BioVectorStore

CURATED_EXTRACTIONS = {
  "entities": [
    {"name": "Metformin", "type": "DRUG", "aliases": ["metformin hydrochloride", "Glucophage"], "source_id": "curated"},
    {"name": "Alzheimer's disease", "type": "DISEASE", "aliases": ["AD", "Alzheimers"], "source_id": "curated"},
    {"name": "Type 2 diabetes", "type": "DISEASE", "aliases": ["T2D", "diabetes mellitus"], "source_id": "curated"},
    {"name": "AMPK", "type": "GENE", "aliases": ["PRKAA1", "AMP-activated protein kinase"], "source_id": "curated"},
    {"name": "APOE", "type": "GENE", "aliases": ["Apolipoprotein E"], "source_id": "curated"},
    {"name": "BRCA1", "type": "GENE", "aliases": ["BRCA1 DNA repair associated"], "source_id": "curated"},
    {"name": "Breast cancer", "type": "DISEASE", "aliases": ["mammary carcinoma"], "source_id": "curated"},
    {"name": "Asthma", "type": "DISEASE", "aliases": ["bronchial asthma"], "source_id": "curated"},
    {"name": "TNF", "type": "GENE", "aliases": ["TNF-alpha", "tumor necrosis factor"], "source_id": "curated"},
    {"name": "Rheumatoid arthritis", "type": "DISEASE", "aliases": ["RA"], "source_id": "curated"},
    {"name": "Adalimumab", "type": "DRUG", "aliases": ["Humira"], "source_id": "curated"},
    {"name": "Insulin", "type": "DRUG", "aliases": ["human insulin"], "source_id": "curated"},
    {"name": "GLP1R", "type": "GENE", "aliases": ["GLP-1 receptor"], "source_id": "curated"},
    {"name": "Semaglutide", "type": "DRUG", "aliases": ["Ozempic", "Wegovy"], "source_id": "curated"},
    {"name": "Obesity", "type": "DISEASE", "aliases": ["adiposity"], "source_id": "curated"}
  ],
  "relationships": [
    {"source": "Metformin", "target": "AMPK", "relation": "ACTIVATES", "confidence": 0.95, "evidence": "Metformin activates AMPK to lower blood glucose."},
    {"source": "AMPK", "target": "Type 2 diabetes", "relation": "ASSOCIATED_WITH", "confidence": 0.90, "evidence": "AMPK dysregulation is central to T2D pathogenesis."},
    {"source": "AMPK", "target": "Alzheimer's disease", "relation": "ASSOCIATED_WITH", "confidence": 0.82, "evidence": "AMPK activation reduces tau phosphorylation in Alzheimer's models."},
    {"source": "Metformin", "target": "Alzheimer's disease", "relation": "TREATS", "confidence": 0.75, "evidence": "Epidemiological studies show metformin reduces Alzheimer's risk in diabetic patients."},
    {"source": "APOE", "target": "Alzheimer's disease", "relation": "ASSOCIATED_WITH", "confidence": 0.98, "evidence": "APOE e4 allele is the strongest genetic risk factor for late-onset Alzheimer's."},
    {"source": "APOE", "target": "Type 2 diabetes", "relation": "ASSOCIATED_WITH", "confidence": 0.70, "evidence": "APOE polymorphisms influence lipid metabolism in Type 2 diabetes."},
    {"source": "BRCA1", "target": "Breast cancer", "relation": "ASSOCIATED_WITH", "confidence": 0.99, "evidence": "Germline mutations in BRCA1 cause familial breast cancer."},
    {"source": "Adalimumab", "target": "TNF", "relation": "INHIBITS", "confidence": 0.96, "evidence": "Adalimumab binds and neutralizes TNF-alpha."},
    {"source": "TNF", "target": "Rheumatoid arthritis", "relation": "ASSOCIATED_WITH", "confidence": 0.94, "evidence": "TNF-alpha drives inflammatory joint destruction in RA."},
    {"source": "TNF", "target": "Asthma", "relation": "ASSOCIATED_WITH", "confidence": 0.78, "evidence": "Elevated TNF-alpha levels are observed in severe refractory asthma."},
    {"source": "Semaglutide", "target": "GLP1R", "relation": "ACTIVATES", "confidence": 0.97, "evidence": "Semaglutide is a potent GLP-1 receptor agonist."},
    {"source": "GLP1R", "target": "Type 2 diabetes", "relation": "ASSOCIATED_WITH", "confidence": 0.95, "evidence": "GLP-1 receptor signaling enhances glucose-dependent insulin secretion."},
    {"source": "GLP1R", "target": "Obesity", "relation": "ASSOCIATED_WITH", "confidence": 0.92, "evidence": "GLP1R activation delays gastric emptying and promotes satiety."}
  ]
}

def main():
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = PROCESSED_DATA_DIR / "merged_extractions.json"
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(CURATED_EXTRACTIONS, f, indent=2)
        
    G = build_graph(CURATED_EXTRACTIONS)
    save_graph(G)
    print(f"✅ Knowledge graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    
    vs = BioVectorStore()
    vs.index_graph_relations(CURATED_EXTRACTIONS["relationships"])
    stats = vs.get_stats()
    print(f"✅ Vector store updated: {stats['text_chunks']} text chunks, {stats['graph_relations']} graph relations.")

if __name__ == "__main__":
    main()
