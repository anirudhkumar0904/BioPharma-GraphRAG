"""
hybrid_retriever.py — The brain of GraphRAG.

Combines:
  1. Graph traversal (multi-hop reasoning through the knowledge graph)
  2. Vector search (semantic similarity from PubMed abstracts)
  3. Structured queries (shared genes, drug repurposing paths)

This is what makes GraphRAG different from regular RAG.
"""
import re
import networkx as nx
from graph_builder import (
    find_shared_genes, find_drug_repurposing,
    get_node_neighborhood, get_graph_summary
)
from vector_store import BioVectorStore


class HybridRetriever:
    def __init__(self, graph: nx.DiGraph, vector_store: BioVectorStore):
        self.G = graph
        self.vs = vector_store

    def classify_query(self, query: str) -> str:
        """
        Classify the query type to choose the right retrieval strategy.
        Simple keyword-based classifier (no LLM needed for this).
        """
        q = query.lower()

        # Pattern: "what genes connect X and Y" / "shared genes between"
        if any(kw in q for kw in ["shared gene", "connect", "common gene", "link between",
                                    "genes connect", "overlap", "in common"]):
            return "shared_genes"

        # Pattern: "what else could drug X treat" / "repurpose" / "other diseases"
        if any(kw in q for kw in ["repurpos", "other disease", "else could", "what else",
                                    "new indication", "off-label"]):
            return "drug_repurposing"

        # Pattern: "tell me about X" / "what is X" / "explore"
        if any(kw in q for kw in ["tell me about", "what is", "describe", "explain",
                                    "explore", "neighborhood", "connections of"]):
            return "explore_entity"

        # Pattern: "how does drug X work" / "mechanism"
        if any(kw in q for kw in ["mechanism", "how does", "how do", "pathway",
                                    "target", "work"]):
            return "mechanism"

        # Default: general question
        return "general"

    def extract_entities_from_query(self, query: str) -> list[str]:
        """Pull out entity names mentioned in the query by matching against graph nodes."""
        found = []
        q_lower = query.lower()

        for node in self.G.nodes():
            if node.lower() in q_lower:
                found.append(node)
            else:
                # Check aliases
                aliases = self.G.nodes[node].get("aliases", [])
                for alias in aliases:
                    if alias.lower() in q_lower:
                        found.append(node)
                        break

        # Sort by length (longest first) to prefer specific matches
        found.sort(key=len, reverse=True)
        return found

    def retrieve(self, query: str, top_k: int = 10) -> dict:
        """
        Main retrieval function — routes to the right strategy
        and combines graph + vector results.
        """
        query_type = self.classify_query(query)
        entities = self.extract_entities_from_query(query)

        context = {
            "query": query,
            "query_type": query_type,
            "matched_entities": entities,
            "graph_results": [],
            "vector_results": [],
            "structured_results": [],
            "graph_summary": get_graph_summary(self.G)
        }

        # ── Strategy 1: Shared Genes ──
        if query_type == "shared_genes" and len(entities) >= 2:
            diseases = [e for e in entities
                       if self.G.nodes.get(e, {}).get("type") == "DISEASE"]
            if len(diseases) >= 2:
                shared = find_shared_genes(self.G, diseases[0], diseases[1])
                context["structured_results"] = shared
                context["strategy"] = f"Shared gene analysis: {diseases[0]} ↔ {diseases[1]}"

        # ── Strategy 2: Drug Repurposing ──
        elif query_type == "drug_repurposing" and entities:
            drugs = [e for e in entities
                    if self.G.nodes.get(e, {}).get("type") == "DRUG"]
            if drugs:
                candidates = find_drug_repurposing(self.G, drugs[0])
                context["structured_results"] = candidates
                context["strategy"] = f"Drug repurposing analysis for: {drugs[0]}"

        # ── Strategy 3: Entity Exploration ──
        elif query_type == "explore_entity" and entities:
            neighborhood = get_node_neighborhood(self.G, entities[0], depth=2)
            context["graph_results"] = [neighborhood]
            context["strategy"] = f"Exploring neighborhood of: {entities[0]}"

        # ── Strategy 4: Mechanism / Pathway ──
        elif query_type == "mechanism" and entities:
            for ent in entities[:2]:
                neighborhood = get_node_neighborhood(self.G, ent, depth=2)
                context["graph_results"].append(neighborhood)
            context["strategy"] = f"Mechanism analysis for: {', '.join(entities[:2])}"

        # ── Default: use both graph neighborhood + vector ──
        else:
            if entities:
                for ent in entities[:2]:
                    neighborhood = get_node_neighborhood(self.G, ent, depth=1)
                    context["graph_results"].append(neighborhood)
            context["strategy"] = "General hybrid retrieval"

        # ── Always add vector search results ──
        vector_results = self.vs.search(query, n_results=top_k)
        context["vector_results"] = vector_results

        return context

    def format_context_for_llm(self, context: dict) -> str:
        """
        Format retrieved context into a string that the LLM can use
        to generate an answer.
        """
        parts = []

        # Graph summary
        parts.append(f"=== KNOWLEDGE GRAPH OVERVIEW ===\n{context['graph_summary']}")

        # Strategy used
        parts.append(f"\n=== RETRIEVAL STRATEGY ===\n{context.get('strategy', 'general')}")

        # Structured results (shared genes, repurposing candidates)
        if context["structured_results"]:
            parts.append("\n=== GRAPH ANALYSIS RESULTS ===")
            for i, result in enumerate(context["structured_results"][:10], 1):
                if "gene" in result:
                    parts.append(f"{i}. Gene: {result['gene']} — connects {result['diseases']}")
                    if result.get("evidence"):
                        parts.append(f"   Evidence: {result['evidence'][:200]}")
                elif "path" in result:
                    parts.append(f"{i}. {result['path']}")
                    if result.get("evidence_chain"):
                        parts.append(f"   Evidence: {result['evidence_chain'][:200]}")

        # Graph neighborhood results
        if context["graph_results"]:
            parts.append("\n=== KNOWLEDGE GRAPH CONNECTIONS ===")
            for neighborhood in context["graph_results"]:
                if isinstance(neighborhood, dict) and "center" in neighborhood:
                    center = neighborhood["center"]
                    parts.append(f"\nEntity: {center}")
                    for node in neighborhood.get("nodes", [])[:20]:
                        parts.append(f"  - {node['name']} ({node['type']})")
                    for edge in neighborhood.get("edges", [])[:20]:
                        parts.append(
                            f"  → {edge['source']} --[{edge['relation']}]--> {edge['target']} "
                            f"(conf: {edge.get('confidence', '?')})"
                        )

        # Vector search results (PubMed + graph text)
        if context["vector_results"]:
            parts.append("\n=== RELEVANT RESEARCH (PubMed & Graph) ===")
            for i, result in enumerate(context["vector_results"][:8], 1):
                source = result.get("source_type", "unknown")
                title = result.get("metadata", {}).get("title", "")
                text = result["text"][:300]
                parts.append(f"\n[{source.upper()} {i}] {title}")
                parts.append(f"{text}...")

        return "\n".join(parts)
