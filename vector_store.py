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


class LazyEmbeddingFunction:
    """Lazy loader for SentenceTransformer to prevent RAM spikes on startup."""
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def __call__(self, input_texts: list[str]) -> list[list[float]]:
        return self.model.encode(input_texts).tolist()


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
        Search for relevant chunks. 
        collection: "text", "graph", or "both"
        """
        query_embedding = self.embedder.encode([query]).tolist()
        results = []

        if collection in ("text", "both"):
            text_count = self.text_collection.count()
            if text_count > 0:
                text_results = self.text_collection.query(
                    query_embeddings=query_embedding,
                    n_results=min(n_results, text_count)
                )
                for i, doc in enumerate(text_results["documents"][0]):
                    results.append({
                        "text": doc,
                        "metadata": text_results["metadatas"][0][i],
                        "distance": text_results["distances"][0][i],
                        "source_type": "pubmed"
                    })

        if collection in ("graph", "both"):
            graph_count = self.graph_collection.count()
            if graph_count > 0:
                graph_results = self.graph_collection.query(
                    query_embeddings=query_embedding,
                    n_results=min(n_results, graph_count)
                )
                for i, doc in enumerate(graph_results["documents"][0]):
                    results.append({
                        "text": doc,
                        "metadata": graph_results["metadatas"][0][i],
                        "distance": graph_results["distances"][0][i],
                        "source_type": "graph"
                    })

        # Sort by relevance (lower distance = better)
        results.sort(key=lambda x: x["distance"])
        return results[:n_results]

    def get_stats(self) -> dict:
        return {
            "text_chunks": self.text_collection.count(),
            "graph_relations": self.graph_collection.count()
        }
