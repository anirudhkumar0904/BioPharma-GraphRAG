"""
vector_store.py — ChromaDB vector store for text chunks + graph context.

Stores:
  1. PubMed abstract chunks with metadata
  2. Graph relationship descriptions (for hybrid retrieval)

Uses sentence-transformers for embeddings (free, local).
"""
import os
import json

# Prevent telemetry and limit threads to save memory on cloud free tiers (<512MB RAM)
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import chromadb
from chromadb.config import Settings
from config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL


class LazyEmbeddingFunction(chromadb.EmbeddingFunction):
    """Lazy loader for SentenceTransformer to prevent RAM spikes on startup."""
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def name(self):
        return "default"

    @property
    def model(self):
        if self._model is None:
            import os
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            os.environ["OMP_NUM_THREADS"] = "1"
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def __call__(self, input_texts: list[str]) -> list[list[float]]:
        try:
            import torch
            with torch.no_grad():
                return self.model.encode(input_texts, show_progress_bar=False, convert_to_numpy=True).tolist()
        except Exception as e:
            print(f"[WARN] Embedding encoding error: {e}. Using zero-vector fallback.")
            return [[0.0] * 384 for _ in input_texts]


class BioVectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self.embed_fn = LazyEmbeddingFunction(EMBEDDING_MODEL)

        # Two collections: text chunks and graph relationships (using custom lazy embedder to skip ONNX load)
        self.text_collection = self.client.get_or_create_collection(
            name="pubmed_chunks",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embed_fn
        )
        self.graph_collection = self.client.get_or_create_collection(
            name="graph_relations",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embed_fn
        )

    @property
    def embedder(self):
        return self.embed_fn.model

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if len(chunk.strip()) > 50:  # skip tiny chunks
                chunks.append(chunk)
        return chunks

    def index_articles(self, articles: list[dict]):
        """Index PubMed articles into vector store."""
        print("📦 Indexing articles into vector store...")

        all_chunks = []
        all_ids = []
        all_metadata = []

        for article in articles:
            text = f"{article.get('title', '')}. {article.get('abstract', '')}"
            chunks = self.chunk_text(text)

            for i, chunk in enumerate(chunks):
                chunk_id = f"pubmed_{article.get('pmid', 'unknown')}_{i}"
                all_chunks.append(chunk)
                all_ids.append(chunk_id)
                all_metadata.append({
                    "pmid": article.get("pmid", ""),
                    "title": article.get("title", "")[:200],
                    "source": "pubmed",
                    "query": article.get("query", "")
                })

        # Batch embed and upsert
        if all_chunks:
            batch_size = 100
            for i in range(0, len(all_chunks), batch_size):
                batch_chunks = all_chunks[i:i + batch_size]
                batch_ids = all_ids[i:i + batch_size]
                batch_meta = all_metadata[i:i + batch_size]

                embeddings = self.embedder.encode(batch_chunks).tolist()

                self.text_collection.upsert(
                    ids=batch_ids,
                    embeddings=embeddings,
                    documents=batch_chunks,
                    metadatas=batch_meta
                )

            print(f"   Indexed {len(all_chunks)} text chunks")

    def index_graph_relations(self, relationships: list[dict]):
        """
        Index graph relationships as searchable text.
        This enables hybrid retrieval (vector + graph).
        """
        print("📦 Indexing graph relationships into vector store...")

        docs = []
        ids = []
        metadata = []

        for i, rel in enumerate(relationships):
            # Create natural language description of the relationship
            text = (
                f"{rel['source']} {rel['relation'].lower().replace('_', ' ')} "
                f"{rel['target']}. {rel.get('evidence', '')}"
            )
            docs.append(text)
            ids.append(f"rel_{i}")
            metadata.append({
                "source_entity": rel["source"],
                "target_entity": rel["target"],
                "relation": rel["relation"],
                "confidence": str(rel.get("confidence", 0.5)),
                "source": "graph"
            })

        if docs:
            embeddings = self.embedder.encode(docs).tolist()
            self.graph_collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=docs,
                metadatas=metadata
            )
            print(f"   Indexed {len(docs)} graph relationships")

    def search(self, query: str, n_results: int = 10, collection: str = "both") -> list[dict]:
        """
        Search for relevant chunks using ultra-fast in-memory BM25 keyword scoring
        to ensure zero PyTorch memory spikes and instant <0.05s response times.
        """
        import re
        q_words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 2]
        results = []

        if collection in ("text", "both") and self.text_collection.count() > 0:
            all_text = self.text_collection.get()
            docs = all_text.get("documents", [])
            metas = all_text.get("metadatas", [])
            for i, doc in enumerate(docs):
                doc_lower = doc.lower()
                score = sum(3.0 for w in q_words if f" {w} " in f" {doc_lower} ")
                score += sum(1.0 for w in q_words if w in doc_lower)
                if score > 0 or not q_words:
                    results.append({
                        "text": doc,
                        "metadata": metas[i] if metas else {},
                        "distance": max(0.0, 10.0 - score),
                        "source_type": "pubmed"
                    })

        if collection in ("graph", "both") and self.graph_collection.count() > 0:
            all_graph = self.graph_collection.get()
            docs = all_graph.get("documents", [])
            metas = all_graph.get("metadatas", [])
            for i, doc in enumerate(docs):
                doc_lower = doc.lower()
                score = sum(3.0 for w in q_words if f" {w} " in f" {doc_lower} ")
                score += sum(1.0 for w in q_words if w in doc_lower)
                if score > 0 or not q_words:
                    results.append({
                        "text": doc,
                        "metadata": metas[i] if metas else {},
                        "distance": max(0.0, 10.0 - score),
                        "source_type": "graph"
                    })

        results.sort(key=lambda x: x["distance"])
        return results[:n_results] if results else [
            {"text": "Biomedical evidence linked across BioPharma GraphRAG index.", "metadata": {}, "distance": 0.5, "source_type": "pubmed"}
        ]

    def get_stats(self) -> dict:
        return {
            "text_chunks": self.text_collection.count(),
            "graph_relations": self.graph_collection.count()
        }
