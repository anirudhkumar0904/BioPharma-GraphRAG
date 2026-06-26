"""
graph_viz.py — Interactive graph visualization for Streamlit using pyvis.
"""
import networkx as nx
from pyvis.network import Network
import tempfile
import os


# Color scheme for entity types
TYPE_COLORS = {
    "DRUG": "#FF6B6B",        # coral red
    "DISEASE": "#4ECDC4",     # teal
    "GENE": "#FFE66D",        # yellow
    "PROTEIN": "#A8E6CF",     # mint
    "PATHWAY": "#DDA0DD",     # plum
    "SIDE_EFFECT": "#FF8C42", # orange
    "UNKNOWN": "#95A5A6",     # grey
}

TYPE_SHAPES = {
    "DRUG": "diamond",
    "DISEASE": "dot",
    "GENE": "triangle",
    "PROTEIN": "square",
    "PATHWAY": "star",
    "SIDE_EFFECT": "triangleDown",
    "UNKNOWN": "dot",
}


def create_subgraph_viz(
    G: nx.DiGraph,
    center_node: str = None,
    depth: int = 2,
    max_nodes: int = 60,
    height: str = "600px",
    width: str = "100%",
    filter_type: str = None
) -> str:
    """
    Create an interactive pyvis visualization of a subgraph.
    Returns HTML string for Streamlit.
    """
    # Get subgraph
    if center_node and center_node in G:
        # BFS to get neighborhood
        nodes_to_show = {center_node}
        frontier = {center_node}
        for _ in range(depth):
            next_frontier = set()
            for n in frontier:
                for neighbor in nx.all_neighbors(G, n):
                    if len(nodes_to_show) < max_nodes:
                        nodes_to_show.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
        subG = G.subgraph(nodes_to_show)
    else:
        # Show most connected nodes
        centrality = nx.degree_centrality(G)
        top_nodes = sorted(centrality, key=centrality.get, reverse=True)[:max_nodes]
        subG = G.subgraph(top_nodes)

    if filter_type and filter_type.strip() and filter_type.strip().upper() != "ALL":
        ft = filter_type.strip().upper()
        keep = [n for n, d in subG.nodes(data=True) if d.get("type", "").upper() == ft or (center_node and n.upper() == center_node.upper())]
        if keep:
            subG = subG.subgraph(keep)

    # Create pyvis network
    net = Network(
        height=height, width=width,
        bgcolor="#0a0a0a",
        font_color="#ffffff",
        directed=True,
        notebook=False
    )

    # Physics settings for nice layout
    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 100,
          "springConstant": 0.05
        },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "stabilization": {"iterations": 100}
      },
      "nodes": {
        "font": {"size": 13, "face": "monospace", "color": "#f8fafc"}
      },
      "edges": {
        "color": {"color": "#475569", "highlight": "#38bdf8", "hover": "#0ea5e9"},
        "smooth": {"type": "dynamic"},
        "font": {"size": 10, "align": "horizontal", "color": "#94a3b8", "background": "rgba(15,23,42,0.85)"}
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 150,
        "hideEdgesOnDrag": false
      }
    }
    """)

    # Add nodes
    for node in subG.nodes():
        data = subG.nodes[node]
        ntype = data.get("type", "UNKNOWN")
        color = TYPE_COLORS.get(ntype, TYPE_COLORS["UNKNOWN"])
        shape = TYPE_SHAPES.get(ntype, "dot")

        # Centrality & Degree calculation
        degree = subG.degree(node)
        centrality_val = round(min(1.0, degree / max(1, len(subG.nodes())) * 4 + 0.3), 2)
        size = 18 + degree * 4.5

        # Highlight center node
        is_center = center_node and (node.upper() == center_node.upper() or center_node.upper() in [a.upper() for a in data.get("aliases", [])])
        border_width = 5 if is_center else 1.5
        border_color = "#38bdf8" if is_center else "rgba(255,255,255,0.4)"
        if is_center:
            size = max(size, 36)

        title = f"{node}\nCategory: {ntype}\nCentrality Score: {centrality_val}\nInteractome Degree: {degree}"
        aliases = data.get("aliases", [])
        if aliases:
            title += f"\nOntology Aliases: {', '.join(aliases[:3])}"

        net.add_node(
            node,
            label=node,
            title=title,
            color={"background": color, "border": border_color, "highlight": {"background": color, "border": "#38bdf8"}},
            shape=shape,
            size=size,
            borderWidth=border_width
        )

    # Add edges
    for u, v, data in subG.edges(data=True):
        relation = data.get("relation", "")
        confidence = data.get("confidence", 0.5)
        evidence = data.get("evidence", "")[:120]

        width = 1.5 + confidence * 3
        color = "#334155" if confidence < 0.5 else "#64748b"

        title = f"Relation: {relation}\nConfidence Score: {confidence:.2f}"
        if evidence:
            title += f"\nEvidence: {evidence}..."

        net.add_edge(u, v, title=title, label=relation, width=width, color=color)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    net.save_graph(tmp.name)
    tmp.close()

    with open(tmp.name, "r", encoding="utf-8") as f:
        html = f.read()

    os.unlink(tmp.name)

    cytoscape_controls_and_drawer = """
    <!-- Top Left: Cytoscape Legends -->
    <div style="position: absolute; top: 16px; left: 16px; background: rgba(15, 23, 42, 0.94); border: 1px solid rgba(56, 189, 248, 0.4); padding: 14px 18px; border-radius: 10px; z-index: 1000; font-family: monospace; font-size: 11.5px; color: #f8fafc; backdrop-filter: blur(12px); box-shadow: 0 10px 35px rgba(0,0,0,0.8);">
      <div style="font-weight: 700; margin-bottom: 10px; color: #38bdf8; letter-spacing: 0.8px; border-bottom: 1px solid #334155; padding-bottom: 6px;">🕸️ CYTOSCAPE WORKSTATION LEGEND</div>
      <div style="font-weight: 700; color: #94a3b8; font-size: 10px; margin-bottom: 6px;">NODE TOPOLOGY CATEGORIES</div>
      <div style="display: flex; align-items: center; gap: 8px; margin: 5px 0;"><span style="width:10px; height:10px; border-radius:50%; background:#FFE66D; display:inline-block; box-shadow: 0 0 8px #FFE66D;"></span> GENE / TARGET (Receptor/Kinase)</div>
      <div style="display: flex; align-items: center; gap: 8px; margin: 5px 0;"><span style="width:10px; height:10px; border-radius:50%; background:#4ECDC4; display:inline-block; box-shadow: 0 0 8px #4ECDC4;"></span> DISEASE / CLINICAL INDICATION</div>
      <div style="display: flex; align-items: center; gap: 8px; margin: 5px 0;"><span style="width:10px; height:10px; border-radius:2px; transform: rotate(45deg); background:#FF6B6B; display:inline-block; box-shadow: 0 0 8px #FF6B6B;"></span> DRUG / THERAPEUTIC CANDIDATE</div>
      <div style="display: flex; align-items: center; gap: 8px; margin: 5px 0;"><span style="width:10px; height:10px; border-radius:2px; background:#A8E6CF; display:inline-block;"></span> PATHWAY / INTERACTOME COMPLEX</div>
      <div style="font-weight: 700; color: #94a3b8; font-size: 10px; margin: 10px 0 6px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px;">EDGE RELATIONSHIPS</div>
      <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;"><span style="width:18px; height:2px; background:#38bdf8; display:inline-block;"></span> Direct Biological Assay Target</div>
      <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;"><span style="width:18px; height:2px; border-top: 2px dashed #64748b; display:inline-block;"></span> Clinical Association / GWAS Link</div>
      <div style="margin-top: 10px; font-size: 10px; color: #38bdf8; background: rgba(56,189,248,0.1); padding: 4px 8px; border-radius: 4px;">💡 Click any node for telemetry inspection</div>
    </div>

    <!-- Top Right: Graph Locator & Navigation Toolbar -->
    <div style="position: absolute; top: 16px; right: 16px; display: flex; gap: 8px; z-index: 1000; font-family: monospace;">
      <input id="graph-search-box" type="text" placeholder="Locate node (e.g. CFTR)..." style="background: rgba(15, 23, 42, 0.94); border: 1px solid #334155; color: #ffffff; padding: 8px 12px; border-radius: 6px; font-size: 12px; font-family: monospace; outline: none; width: 200px; backdrop-filter: blur(10px);" onkeydown="if(event.key==='Enter') locateGraphNode()">
      <button onclick="locateGraphNode()" style="background: #0284c7; color: #ffffff; border: none; padding: 8px 14px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 12px; transition: background 0.2s;">🎯 Search</button>
      <button onclick="resetGraphView()" style="background: rgba(30, 41, 59, 0.94); color: #38bdf8; border: 1px solid #38bdf8; padding: 8px 14px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 12px; backdrop-filter: blur(10px); transition: all 0.2s;">🔄 Reset View</button>
    </div>

    <!-- Bottom Right: Cytoscape Metadata Side Panel Drawer -->
    <div id="graph-side-panel" style="position: absolute; bottom: 16px; right: 16px; width: 310px; background: rgba(15, 23, 42, 0.96); border: 1px solid #38bdf8; border-radius: 12px; padding: 18px; z-index: 1000; font-family: monospace; color: #f8fafc; backdrop-filter: blur(16px); box-shadow: 0 15px 40px rgba(0,0,0,0.85); display: none;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 12px;">
        <span style="font-size: 11px; color: #38bdf8; font-weight: 700; letter-spacing: 0.5px;">🧬 NODE TELEMETRY INSPECTOR</span>
        <span onclick="document.getElementById('graph-side-panel').style.display='none'" style="cursor: pointer; color: #94a3b8; font-size: 14px;">✕</span>
      </div>
      <div id="side-panel-title" style="font-size: 16px; font-weight: 700; color: #ffffff; margin-bottom: 6px; word-break: break-all;"></div>
      <div style="font-size: 11px; color: #cbd5e1; line-height: 1.8;">
        <div><b style="color:#94a3b8;">Entity Class:</b> <span id="side-panel-cat" style="color:#38bdf8; font-weight:700;"></span></div>
        <div><b style="color:#94a3b8;">Topology Degree:</b> <span id="side-panel-deg"></span> connected targets</div>
        <div><b style="color:#94a3b8;">First-Degree Targets:</b></div>
        <div id="side-panel-neighbors" style="background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; margin: 6px 0; max-height: 90px; overflow-y: auto; font-size: 10.5px; color: #38bdf8;"></div>
      </div>
      <div style="margin-top: 12px; padding-top: 8px; border-top: 1px dashed #334155; font-size: 10px; color: #64748b; text-align: center;">
        Cytoscape / Neo4j Bloom Traversal Telemetry
      </div>
    </div>

    <script type="text/javascript">
      function locateGraphNode() {
        var query = document.getElementById('graph-search-box').value.trim().toLowerCase();
        if(!query || typeof nodes === 'undefined') return;
        var all = nodes.get();
        var match = all.find(function(n) { return n.id.toLowerCase() === query || n.id.toLowerCase().includes(query); });
        if(match) {
          network.focus(match.id, {scale: 1.6, animation: {duration: 650, easingFunction: 'easeInOutQuad'}});
          network.selectNodes([match.id]);
          triggerNodeInspection(match.id);
        } else {
          alert('Entity "' + query + '" not located in active subgraph viewport.');
        }
      }

      function resetGraphView() {
        if(typeof network === 'undefined') return;
        network.fit({animation: {duration: 650, easingFunction: 'easeInOutQuad'}});
        var all = nodes.get();
        var reset = all.map(function(n) { return {id: n.id, opacity: 1.0, font: {color: '#f8fafc', size: 13}}; });
        nodes.update(reset);
        document.getElementById('graph-side-panel').style.display = 'none';
      }

      function triggerNodeInspection(selNodeId) {
        var conn = network.getConnectedNodes(selNodeId);
        var panel = document.getElementById('graph-side-panel');
        document.getElementById('side-panel-title').innerText = selNodeId;
        
        // Infer category from active dataset
        var nObj = nodes.get(selNodeId);
        var cat = "BIOMEDICAL ENTITY";
        if(nObj && nObj.color && nObj.color.background) {
          var bg = nObj.color.background.toUpperCase();
          if(bg === '#FFE66D') cat = "TARGET GENE (Kinase/Receptor)";
          if(bg === '#4ECDC4') cat = "CLINICAL INDICATION (Disease)";
          if(bg === '#FF6B6B') cat = "THERAPEUTIC CANDIDATE (Drug)";
        }
        document.getElementById('side-panel-cat').innerText = cat;
        document.getElementById('side-panel-deg').innerText = conn.length;
        document.getElementById('side-panel-neighbors').innerText = conn.length > 0 ? conn.join(' · ') : 'Isolated Factual Extraction Node';
        panel.style.display = 'block';

        // Highlight 1st degree neighbors & fade unrelated nodes
        var all = nodes.get();
        var upd = all.map(function(n) {
          if(n.id === selNodeId || conn.includes(n.id)) {
            return {id: n.id, opacity: 1.0, font: {color: '#ffffff', size: n.id === selNodeId ? 16 : 14}};
          } else {
            return {id: n.id, opacity: 0.12, font: {color: 'rgba(255,255,255,0.08)'}};
          }
        });
        nodes.update(upd);
      }

      setTimeout(function() {
        if (typeof network !== 'undefined') {
          network.on("click", function (params) {
            if (params.nodes.length > 0) {
              var sel = params.nodes[0];
              triggerNodeInspection(sel);
            } else {
              resetGraphView();
            }
          });
        }
      }, 450);
    </script>
    """
    return html.replace("</body>", cytoscape_controls_and_drawer + "\n</body>")


def create_path_viz(
    G: nx.DiGraph,
    paths: list[dict],
    height: str = "400px"
) -> str:
    """
    Visualize drug repurposing paths or shared gene connections.
    """
    net = Network(
        height=height, width="100%",
        bgcolor="#0a0a0a", font_color="#ffffff",
        directed=True, notebook=False
    )

    net.set_options("""
    {
      "physics": {"enabled": false},
      "layout": {"hierarchical": {"direction": "LR", "sortMethod": "directed"}},
      "nodes": {"font": {"size": 16, "face": "monospace"}},
      "edges": {"font": {"size": 12, "color": "#aaaaaa"}, "smooth": true}
    }
    """)

    added_nodes = set()
    for path_info in paths[:10]:
        # Handle both path formats
        if "path" in path_info:
            # Drug repurposing: "Drug → Gene → Disease"
            parts = [p.strip() for p in path_info["path"].split("→")]
            types = ["DRUG", "GENE", "DISEASE"]
        elif "gene" in path_info:
            # Shared genes: gene connects diseases
            parts = [path_info["diseases"][0], path_info["gene"], path_info["diseases"][1]]
            types = ["DISEASE", "GENE", "DISEASE"]
        else:
            continue

        for i, part in enumerate(parts):
            if part not in added_nodes:
                ntype = types[i] if i < len(types) else "UNKNOWN"
                color = TYPE_COLORS.get(ntype, "#95A5A6")
                net.add_node(part, label=part, color=color,
                           shape=TYPE_SHAPES.get(ntype, "dot"), size=25)
                added_nodes.add(part)

        for i in range(len(parts) - 1):
            net.add_edge(parts[i], parts[i + 1], color="#666666", width=2)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    net.save_graph(tmp.name)
    tmp.close()

    with open(tmp.name, "r", encoding="utf-8") as f:
        html = f.read()

    os.unlink(tmp.name)
    return html
