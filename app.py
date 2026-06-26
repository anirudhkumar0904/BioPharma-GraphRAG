"""
app.py — Streamlit UI for BioPharma GraphRAG.

Features:
  1. Interactive knowledge graph visualization
  2. Natural language query interface
  3. Multi-hop reasoning (shared genes, drug repurposing)
  4. Hallucination detection with trust scores
  5. Evidence chain display
"""
import streamlit as st
import streamlit.components.v1 as components
import networkx as nx
from collections import defaultdict

from graph_builder import load_graph, get_graph_summary
from vector_store import BioVectorStore
from hybrid_retriever import HybridRetriever
from answer_generator import generate_answer_with_verification
from graph_viz import create_subgraph_viz, create_path_viz


# ── Page Config ──
st.set_page_config(
    page_title="BioPharma GraphRAG",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ──
st.markdown("""
<style>
    .main { background-color: #0a0a0a; }
    .stApp { background-color: #0a0a0a; color: #e0e0e0; }

    .trust-badge {
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: bold;
        display: inline-block;
        margin: 8px 0;
    }
    .trust-high { background: #1a3a2a; border: 1px solid #4ECDC4; color: #4ECDC4; }
    .trust-medium { background: #3a3a1a; border: 1px solid #FFE66D; color: #FFE66D; }
    .trust-low { background: #3a1a1a; border: 1px solid #FF6B6B; color: #FF6B6B; }

    .entity-tag {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        margin: 2px;
        font-weight: 600;
    }
    .tag-drug { background: #FF6B6B33; color: #FF6B6B; border: 1px solid #FF6B6B55; }
    .tag-disease { background: #4ECDC433; color: #4ECDC4; border: 1px solid #4ECDC455; }
    .tag-gene { background: #FFE66D33; color: #FFE66D; border: 1px solid #FFE66D55; }

    .claim-card {
        padding: 10px;
        margin: 5px 0;
        border-radius: 8px;
        border-left: 3px solid;
    }
    .claim-supported { border-color: #4ECDC4; background: #4ECDC410; }
    .claim-partial { border-color: #FFE66D; background: #FFE66D10; }
    .claim-unsupported { border-color: #FF6B6B; background: #FF6B6B10; }
</style>
""", unsafe_allow_html=True)


# ── Load Resources ──
@st.cache_resource
def load_resources():
    """Load graph and vector store once."""
    try:
        G = load_graph()
        vs = BioVectorStore()
        retriever = HybridRetriever(G, vs)
        return G, vs, retriever
    except Exception as e:
        st.error(f"⚠️ Resources not found. Run the pipeline first:\n```\npython pipeline.py\n```\nError: {e}")
        return None, None, None


G, vs, retriever = load_resources()


# ════════════════════════════════════════════
# Sidebar
# ════════════════════════════════════════════

with st.sidebar:
    st.markdown("# 🧬 BioPharma GraphRAG")
    st.markdown("**Drug-Disease-Gene Knowledge Graph**")
    st.markdown("---")

    if G is not None:
        # Graph stats
        type_counts = defaultdict(int)
        for _, data in G.nodes(data=True):
            type_counts[data.get("type", "UNKNOWN")] += 1

        st.markdown("### 📊 Graph Stats")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Entities", G.number_of_nodes())
        with col2:
            st.metric("Relations", G.number_of_edges())

        st.markdown("**Entity Breakdown:**")
        for etype, count in sorted(type_counts.items()):
            emoji = {"DRUG": "💊", "DISEASE": "🦠", "GENE": "🧬",
                     "PROTEIN": "🔬", "PATHWAY": "🔀", "SIDE_EFFECT": "⚠️"}.get(etype, "❓")
            st.markdown(f"{emoji} **{etype}**: {count}")

        if vs:
            stats = vs.get_stats()
            st.markdown("### 📦 Vector Store")
            st.markdown(f"Text chunks: **{stats['text_chunks']}**")
            st.markdown(f"Graph relations: **{stats['graph_relations']}**")

    st.markdown("---")
    st.markdown("### 💡 Try These Queries")
    example_queries = [
        "What genes connect diabetes and Alzheimer's?",
        "What other diseases could Metformin treat?",
        "Tell me about APOE and its disease connections",
        "How does insulin resistance relate to neurodegeneration?",
        "What drugs target BRCA1?",
        "Find drug repurposing candidates for Alzheimer's",
        "What are the shared pathways between obesity and cancer?",
        "Explain the mechanism of SGLT2 inhibitors",
    ]
    for q in example_queries:
        if st.button(q, key=f"ex_{q[:20]}", use_container_width=True):
            st.session_state["query_input"] = q

    st.markdown("---")
    st.markdown(
        "**Data Sources:** PubMed, Open Targets  \n"
        "**Built with:** NetworkX, ChromaDB, OpenAI  \n"
        "**By:** Madhu | SASTRA University"
    )


# ════════════════════════════════════════════
# Main Content
# ════════════════════════════════════════════

if G is None:
    st.stop()

# ── Tabs ──
tab1, tab2, tab3 = st.tabs(["🔍 Query", "🕸️ Graph Explorer", "📋 About"])

# ═══════ TAB 1: Query Interface ═══════
with tab1:
    st.markdown("## Ask the Knowledge Graph")

    # Query input
    query = st.text_input(
        "Enter your question about drug-disease-gene interactions:",
        value=st.session_state.get("query_input", ""),
        placeholder="e.g., What genes connect diabetes and Alzheimer's?",
        key="main_query"
    )

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)

    if search_clicked and query:
        with st.spinner("Retrieving from knowledge graph + vector store..."):
            # Retrieve context
            context = retriever.retrieve(query)
            formatted_context = retriever.format_context_for_llm(context)

        # Show retrieval info
        with st.expander("📡 Retrieval Details", expanded=False):
            st.markdown(f"**Strategy:** {context.get('strategy', 'general')}")
            st.markdown(f"**Query Type:** `{context.get('query_type', 'general')}`")
            st.markdown(f"**Matched Entities:** {', '.join(context.get('matched_entities', [])) or 'None'}")
            st.markdown(f"**Vector results:** {len(context.get('vector_results', []))}")
            st.markdown(f"**Graph results:** {len(context.get('graph_results', []))}")
            st.markdown(f"**Structured results:** {len(context.get('structured_results', []))}")

        # Visualize paths if we have structured results
        if context.get("structured_results"):
            st.markdown("### 🗺️ Discovered Paths")
            path_html = create_path_viz(G, context["structured_results"])
            components.html(path_html, height=420, scrolling=True)

        # Generate answer with hallucination check
        with st.spinner("Generating answer + checking for hallucinations..."):
            result = generate_answer_with_verification(query, formatted_context)

        # Trust badge
        score = result.get("trust_score", -1)
        if score >= 0.8:
            badge_class = "trust-high"
        elif score >= 0.5:
            badge_class = "trust-medium"
        else:
            badge_class = "trust-low"

        st.markdown(
            f'<div class="trust-badge {badge_class}">{result["trust_badge"]}</div>',
            unsafe_allow_html=True
        )

        # Answer
        st.markdown("### 📝 Answer")
        st.markdown(result["answer"])

        # Hallucination report
        report = result.get("hallucination_report", {})
        claims = report.get("claims", [])
        if claims:
            with st.expander(f"🔬 Hallucination Report ({len(claims)} claims verified)", expanded=False):
                st.markdown(f"**Overall Trust Score:** {report.get('overall_score', 'N/A')}")
                st.markdown(f"**Summary:** {report.get('summary', '')}")
                st.markdown("---")

                for claim in claims:
                    verdict = claim.get("verdict", "UNKNOWN")
                    if verdict == "SUPPORTED":
                        css_class = "claim-supported"
                        icon = "✅"
                    elif verdict == "PARTIALLY_SUPPORTED":
                        css_class = "claim-partial"
                        icon = "🟡"
                    else:
                        css_class = "claim-unsupported"
                        icon = "❌"

                    st.markdown(
                        f'<div class="claim-card {css_class}">'
                        f'{icon} <b>{claim.get("claim", "")}</b><br>'
                        f'<small>{claim.get("evidence", "")}</small>'
                        f'</div>',
                        unsafe_allow_html=True
                    )


# ═══════ TAB 2: Graph Explorer ═══════
with tab2:
    st.markdown("## 🕸️ Knowledge Graph Explorer")

    col_search, col_depth = st.columns([3, 1])

    with col_search:
        # Entity search with autocomplete
        all_nodes = sorted(G.nodes()) if G else []
        explore_node = st.selectbox(
            "Select an entity to explore:",
            options=["(Show overview)"] + all_nodes,
            index=0
        )

    with col_depth:
        depth = st.slider("Hops", 1, 3, 2)

    # Render graph
    if explore_node == "(Show overview)":
        html = create_subgraph_viz(G, center_node=None, depth=1, max_nodes=50)
    else:
        html = create_subgraph_viz(G, center_node=explore_node, depth=depth, max_nodes=60)

    components.html(html, height=650, scrolling=True)

    # Legend
    st.markdown("### Legend")
    legend_cols = st.columns(6)
    for i, (etype, color) in enumerate([
        ("Drug 💊", "#FF6B6B"), ("Disease 🦠", "#4ECDC4"),
        ("Gene 🧬", "#FFE66D"), ("Protein 🔬", "#A8E6CF"),
        ("Pathway 🔀", "#DDA0DD"), ("Side Effect ⚠️", "#FF8C42")
    ]):
        with legend_cols[i]:
            st.markdown(
                f'<span style="color:{color}; font-weight:bold;">● {etype}</span>',
                unsafe_allow_html=True
            )

    # Node details
    if explore_node != "(Show overview)" and explore_node in G:
        st.markdown(f"### Details: {explore_node}")
        node_data = G.nodes[explore_node]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Type:** {node_data.get('type', 'Unknown')}")
            aliases = node_data.get("aliases", [])
            if aliases:
                st.markdown(f"**Aliases:** {', '.join(aliases[:5])}")

        with col2:
            in_degree = G.in_degree(explore_node)
            out_degree = G.out_degree(explore_node)
            st.markdown(f"**Incoming connections:** {in_degree}")
            st.markdown(f"**Outgoing connections:** {out_degree}")

        # Show direct connections
        st.markdown("**Direct Connections:**")
        connections = []
        for neighbor in G.neighbors(explore_node):
            edge = G[explore_node][neighbor]
            connections.append({
                "Target": neighbor,
                "Type": G.nodes[neighbor].get("type", ""),
                "Relation": edge.get("relation", ""),
                "Confidence": f"{float(edge.get('confidence', 0) or 0):.2f}"
            })
        for pred in G.predecessors(explore_node):
            edge = G[pred][explore_node]
            connections.append({
                "Target": pred,
                "Type": G.nodes[pred].get("type", ""),
                "Relation": f"← {edge.get('relation', '')}",
                "Confidence": f"{float(edge.get('confidence', 0) or 0):.2f}"
            })

        if connections:
            st.dataframe(connections, use_container_width=True)


# ═══════ TAB 3: About ═══════
with tab3:
    st.markdown("""
    ## 🧪 BioPharma GraphRAG

    A **Graph-based Retrieval Augmented Generation** system for exploring
    drug-disease-gene interactions and discovering potential drug repurposing
    opportunities.

    ### How It Works

    1. **Data Collection** — Pulls real biomedical data from PubMed (research abstracts)
       and Open Targets (drug-gene-disease associations)

    2. **Entity Extraction** — Uses LLM to extract drugs, diseases, genes, and their
       relationships from unstructured text. Structured API data is parsed directly.

    3. **Knowledge Graph** — Builds a directed graph where nodes are biomedical entities
       and edges are their relationships (targets, treats, associated_with, etc.)

    4. **Hybrid Retrieval** — Combines graph traversal (multi-hop reasoning) with
       vector similarity search to find the most relevant context for any question

    5. **Answer Generation** — LLM generates answers grounded in the retrieved context

    6. **Hallucination Detection** — Every claim in the answer is verified against
       the source context, producing a trust score

    ### What Makes This Special

    | Feature | Regular RAG | This GraphRAG |
    |---------|------------|---------------|
    | "What genes connect diabetes and Alzheimer's?" | ❌ Can't traverse | ✅ Multi-hop graph query |
    | "What else could Metformin treat?" | ❌ No path reasoning | ✅ Drug → Gene → Disease paths |
    | Evidence chains | ❌ Just snippets | ✅ Full path with confidence |
    | Hallucination check | ❌ No | ✅ Every claim verified |

    ### Data Sources
    - **PubMed** (NCBI) — 300+ research abstracts
    - **Open Targets** — Drug-gene-disease associations for 12 major diseases
    - All data is free and publicly available

    ### Tech Stack
    - **Graph:** NetworkX + PyVis
    - **Vectors:** ChromaDB + sentence-transformers
    - **LLM:** OpenAI GPT-4o-mini (or Ollama for local)
    - **UI:** Streamlit
    - **NLP:** Custom entity extraction pipeline

    ---
    *Built by Madhu — SASTRA University, B.Tech CSE (IoT & Automation)*
    """)
