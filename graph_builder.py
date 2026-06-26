"""
graph_builder.py — Build a NetworkX knowledge graph from extracted entities & relationships.

The graph stores:
  - Nodes: drugs, diseases, genes, proteins, pathways, side effects
  - Edges: relationships with evidence and confidence scores
  - Supports multi-hop traversal for drug repurposing queries
"""
import json
import pickle
import networkx as nx
from collections import defaultdict
from config import GRAPH_PATH, PROCESSED_DATA_DIR


def build_graph(merged_data: dict) -> nx.DiGraph:
    """
    Build a directed knowledge graph from merged entity/relationship data.
    """
    G = nx.DiGraph()

    # ── Add nodes ──
    entity_name_map = {}  # lowercase → canonical name
    for ent in merged_data["entities"]:
        name = ent["name"].strip()
        etype = ent.get("type", "UNKNOWN")
        aliases = ent.get("aliases", [])

        # Add node with attributes
        G.add_node(name, **{
            "type": etype,
            "aliases": aliases,
            "source": ent.get("source_id", ""),
        })

        # Map aliases to canonical name
        entity_name_map[name.lower()] = name
        for alias in aliases:
            entity_name_map[alias.lower()] = name

    # ── Add edges ──
    for rel in merged_data["relationships"]:
        source = rel["source"].strip()
        target = rel["target"].strip()
        relation = rel.get("relation", "ASSOCIATED_WITH")
        evidence = rel.get("evidence", "")
        confidence = rel.get("confidence", 0.5)

        # Resolve to canonical names
        source = entity_name_map.get(source.lower(), source)
        target = entity_name_map.get(target.lower(), target)

        # Ensure nodes exist
        if source not in G:
            G.add_node(source, type="UNKNOWN", aliases=[], source="inferred")
        if target not in G:
            G.add_node(target, type="UNKNOWN", aliases=[], source="inferred")

        # Add or update edge
        if G.has_edge(source, target):
            existing = G[source][target]
            # Append evidence
            existing_evidence = existing.get("evidence", "")
            if evidence and evidence not in existing_evidence:
                existing["evidence"] = f"{existing_evidence} | {evidence}"
            # Keep max confidence
            existing["confidence"] = max(existing.get("confidence", 0), confidence)
            # Track relation types
            existing_relations = set(existing.get("relations", "").split(","))
            existing_relations.add(relation)
            existing["relations"] = ",".join(existing_relations)
        else:
            G.add_edge(source, target, **{
                "relation": relation,
                "relations": relation,
                "evidence": evidence,
                "confidence": confidence,
                "source": rel.get("source_id", "")
            })

    print(f"\n📊 Graph Stats:")
    print(f"   Nodes: {G.number_of_nodes()}")
    print(f"   Edges: {G.number_of_edges()}")

    # Node type breakdown
    type_counts = defaultdict(int)
    for _, data in G.nodes(data=True):
        type_counts[data.get("type", "UNKNOWN")] += 1
    for t, c in sorted(type_counts.items()):
        print(f"   {t}: {c}")

    return G


def save_graph(G: nx.DiGraph, path=None):
    """Save graph to disk."""
    path = path or GRAPH_PATH
    with open(path, "wb") as f:
        pickle.dump(G, f)
    print(f"   Graph saved to {path}")


def load_graph(path=None) -> nx.DiGraph:
    """Load graph from disk."""
    path = path or GRAPH_PATH
    with open(path, "rb") as f:
        return pickle.load(f)


# ════════════════════════════════════════════
# Graph Query Utilities
# ════════════════════════════════════════════

def find_shared_genes(G: nx.DiGraph, disease1: str, disease2: str) -> list[dict]:
    """
    Find genes that connect two diseases.
    This is the key drug repurposing insight!
    """
    genes1 = set()
    genes2 = set()

    for node in G.nodes():
        node_data = G.nodes[node]
        if node_data.get("type") != "GENE":
            continue

        # Check if gene is connected to disease1
        connected_to_d1 = (
            G.has_edge(node, disease1) or G.has_edge(disease1, node) or
            any(n.lower() == disease1.lower() or any(a.lower() == disease1.lower() for a in G.nodes[n].get("aliases", []))
                for n in nx.all_neighbors(G, node) if G.nodes.get(n, {}).get("type") == "DISEASE")
        )
        # Check if gene is connected to disease2
        connected_to_d2 = (
            G.has_edge(node, disease2) or G.has_edge(disease2, node) or
            any(n.lower() == disease2.lower() or any(a.lower() == disease2.lower() for a in G.nodes[n].get("aliases", []))
                for n in nx.all_neighbors(G, node) if G.nodes.get(n, {}).get("type") == "DISEASE")
        )

        if connected_to_d1:
            genes1.add(node)
        if connected_to_d2:
            genes2.add(node)

    shared = genes1 & genes2
    results = []
    for gene in shared:
        # Get evidence from edges
        evidence = []
        for d in [disease1, disease2]:
            if G.has_edge(gene, d):
                evidence.append(G[gene][d].get("evidence", ""))
            if G.has_edge(d, gene):
                evidence.append(G[d][gene].get("evidence", ""))

        results.append({
            "gene": gene,
            "diseases": [disease1, disease2],
            "evidence": " | ".join([e for e in evidence if e])
        })

    return results


def find_drug_repurposing(G: nx.DiGraph, drug: str) -> list[dict]:
    """
    Given a drug, find what OTHER diseases it might treat
    by following: Drug → Gene → Disease paths.
    """
    candidates = []

    # Find genes the drug targets
    target_genes = []
    for neighbor in G.neighbors(drug):
        edge_data = G[drug][neighbor]
        if "TARGETS" in edge_data.get("relations", ""):
            target_genes.append(neighbor)

    # Also check reverse edges
    for predecessor in G.predecessors(drug):
        edge_data = G[predecessor][drug]
        if G.nodes.get(predecessor, {}).get("type") == "GENE":
            target_genes.append(predecessor)

    # For each target gene, find associated diseases
    known_diseases = set()
    for neighbor in G.neighbors(drug):
        if G.nodes.get(neighbor, {}).get("type") == "DISEASE":
            known_diseases.add(neighbor)

    for gene in target_genes:
        for neighbor in nx.all_neighbors(G, gene):
            node_data = G.nodes.get(neighbor, {})
            if node_data.get("type") == "DISEASE" and neighbor not in known_diseases:
                # Get evidence chain
                evidence_chain = []
                if G.has_edge(drug, gene):
                    evidence_chain.append(G[drug][gene].get("evidence", ""))
                elif G.has_edge(gene, drug):
                    evidence_chain.append(G[gene][drug].get("evidence", ""))
                if G.has_edge(gene, neighbor):
                    evidence_chain.append(G[gene][neighbor].get("evidence", ""))
                elif G.has_edge(neighbor, gene):
                    evidence_chain.append(G[neighbor][gene].get("evidence", ""))

                candidates.append({
                    "drug": drug,
                    "potential_disease": neighbor,
                    "via_gene": gene,
                    "evidence_chain": " → ".join([e for e in evidence_chain if e]),
                    "path": f"{drug} → {gene} → {neighbor}"
                })

    return candidates


def get_node_neighborhood(G: nx.DiGraph, node: str, depth: int = 2) -> dict:
    """Get the local subgraph around a node up to N hops."""
    if node not in G:
        # Fuzzy match
        matches = [n for n in G.nodes() if node.lower() in n.lower()]
        if matches:
            node = matches[0]
        else:
            return {"center": node, "nodes": [], "edges": [], "error": "Node not found"}

    # BFS up to depth
    visited = {node}
    frontier = {node}
    all_edges = []

    for _ in range(depth):
        next_frontier = set()
        for n in frontier:
            for neighbor in nx.all_neighbors(G, n):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
                # Collect edges
                if G.has_edge(n, neighbor):
                    all_edges.append({
                        "source": n, "target": neighbor,
                        "relation": G[n][neighbor].get("relation", ""),
                        "confidence": G[n][neighbor].get("confidence", 0)
                    })
                if G.has_edge(neighbor, n):
                    all_edges.append({
                        "source": neighbor, "target": n,
                        "relation": G[neighbor][n].get("relation", ""),
                        "confidence": G[neighbor][n].get("confidence", 0)
                    })
        frontier = next_frontier

    nodes_data = []
    for n in visited:
        data = G.nodes.get(n, {})
        nodes_data.append({
            "name": n,
            "type": data.get("type", "UNKNOWN")
        })

    return {
        "center": node,
        "nodes": nodes_data,
        "edges": all_edges
    }


def get_graph_summary(G: nx.DiGraph) -> str:
    """Generate a text summary of the graph for LLM context."""
    type_counts = defaultdict(int)
    for _, data in G.nodes(data=True):
        type_counts[data.get("type", "UNKNOWN")] += 1

    relation_counts = defaultdict(int)
    for _, _, data in G.edges(data=True):
        relation_counts[data.get("relation", "UNKNOWN")] += 1

    # Top connected nodes
    degree_centrality = nx.degree_centrality(G)
    top_nodes = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:15]

    summary = f"""Knowledge Graph Summary:
- {G.number_of_nodes()} entities, {G.number_of_edges()} relationships
- Entity types: {dict(type_counts)}
- Relationship types: {dict(relation_counts)}
- Most connected entities: {', '.join([f'{n[0]} ({G.nodes[n[0]].get("type","")})' for n in top_nodes])}
"""
    return summary
