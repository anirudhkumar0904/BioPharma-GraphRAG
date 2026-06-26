"""
data_fetcher.py — Pull real biomedical data from free public APIs.

Sources:
  1. PubMed (NCBI E-utilities) — research abstracts
  2. DisGeNET (REST API) — disease-gene associations  
  3. DrugBank (open data XML) — drug-target interactions
  4. Open Targets (GraphQL) — drug-disease-gene links

All sources are FREE for academic/research use.
"""
import json
import time
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from tqdm import tqdm
from config import RAW_DATA_DIR


# ════════════════════════════════════════════
# 1. PubMed — Fetch abstracts by topic
# ════════════════════════════════════════════

def fetch_pubmed_abstracts(query: str, max_results: int = 50) -> list[dict]:
    """
    Search PubMed and fetch abstracts.
    No API key needed (rate-limited to 3 req/sec without key).
    """
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Step 1: Search for PMIDs
    search_url = f"{base}/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance"
    }
    resp = requests.get(search_url, params=params, timeout=30)
    resp.raise_for_status()
    pmids = resp.json()["esearchresult"]["idlist"]

    if not pmids:
        print(f"  No results for query: {query}")
        return []

    # Step 2: Fetch abstracts in batches
    articles = []
    batch_size = 20
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        fetch_url = f"{base}/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml"
        }
        resp = requests.get(fetch_url, params=params, timeout=30)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        for article in root.findall(".//PubmedArticle"):
            title_el = article.find(".//ArticleTitle")
            abstract_el = article.find(".//AbstractText")
            pmid_el = article.find(".//PMID")

            title = title_el.text if title_el is not None and title_el.text else ""
            abstract = abstract_el.text if abstract_el is not None and abstract_el.text else ""
            pmid = pmid_el.text if pmid_el is not None else ""

            if abstract:  # skip articles without abstracts
                articles.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                    "source": "pubmed",
                    "query": query
                })

        time.sleep(0.4)  # respect rate limit

    print(f"  Fetched {len(articles)} abstracts for: {query}")
    return articles


# ════════════════════════════════════════════
# 2. Open Targets — Drug-Disease-Gene links
# ════════════════════════════════════════════

def fetch_open_targets_associations(disease_id: str, disease_name: str, size: int = 50) -> list[dict]:
    """
    Fetch gene associations for a disease from Open Targets (GraphQL API).
    disease_id example: "EFO_0000249" for Alzheimer's
    Completely free, no API key.
    """
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query($diseaseId: String!, $size: Int!) {
      disease(efoId: $diseaseId) {
        name
        associatedTargets(page: {size: $size, index: 0}) {
          rows {
            target {
              approvedSymbol
              approvedName
            }
            score
            datatypeScores {
              componentId: id
              score
            }
          }
        }
      }
    }
    """
    variables = {"diseaseId": disease_id, "size": size}

    try:
        resp = requests.post(url, json={"query": query, "variables": variables}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        associations = []
        disease_data = (data.get("data") or {}).get("disease") or {}
        if not disease_data:
            return []

        rows = (disease_data.get("associatedTargets") or {}).get("rows", []) or []
        for row in rows:
            target = row.get("target", {})
            associations.append({
                "disease_id": disease_id,
                "disease_name": disease_name,
                "gene_symbol": target.get("approvedSymbol", ""),
                "gene_name": target.get("approvedName", ""),
                "association_score": row.get("score", 0),
                "source": "open_targets"
            })

        print(f"  Fetched {len(associations)} gene associations for {disease_name}")
        return associations

    except Exception as e:
        print(f"  Error fetching Open Targets for {disease_name}: {e}")
        return []


def fetch_open_targets_drugs(disease_id: str, disease_name: str, size: int = 30) -> list[dict]:
    """
    Fetch known drugs for a disease from Open Targets.
    """
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query($diseaseId: String!, $size: Int!) {
      disease(efoId: $diseaseId) {
        knownDrugs(size: $size) {
          rows {
            drug {
              name
              mechanismsOfAction {
                rows {
                  mechanismOfAction
                  targets {
                    approvedSymbol
                  }
                }
              }
            }
            phase
            status
          }
        }
      }
    }
    """
    variables = {"diseaseId": disease_id, "size": size}

    try:
        resp = requests.post(url, json={"query": query, "variables": variables}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        drugs = []
        disease_data = (data.get("data") or {}).get("disease") or {}
        if not disease_data:
            return []

        rows = (disease_data.get("knownDrugs") or {}).get("rows", []) or []
        for row in rows:
            drug = row.get("drug") or {}
            moa_rows = (drug.get("mechanismsOfAction") or {}).get("rows", []) or []
            targets = []
            moa_text = ""
            for moa in moa_rows:
                moa_text = moa.get("mechanismOfAction", "")
                for t in (moa.get("targets") or []):
                    targets.append(t.get("approvedSymbol", ""))

            drugs.append({
                "disease_id": disease_id,
                "disease_name": disease_name,
                "drug_name": drug.get("name", ""),
                "phase": row.get("phase", ""),
                "status": row.get("status", ""),
                "mechanism": moa_text,
                "gene_targets": targets,
                "source": "open_targets"
            })

        print(f"  Fetched {len(drugs)} drugs for {disease_name}")
        return drugs

    except Exception as e:
        print(f"  Error fetching drugs for {disease_name}: {e}")
        return []


# ════════════════════════════════════════════
# 3. Master Data Fetch — All diseases
# ════════════════════════════════════════════

# Disease IDs from EFO (Experimental Factor Ontology) — used by Open Targets
DISEASE_CATALOG = {
    "Alzheimer's disease":      "EFO_0000249",
    "Type 2 diabetes":          "EFO_0001360",
    "Parkinson's disease":      "EFO_0002508",
    "Breast cancer":            "EFO_0000305",
    "Lung cancer":              "EFO_0001071",
    "Obesity":                  "EFO_0001073",
    "Hypertension":             "EFO_0000537",
    "Major depressive disorder":"EFO_0003761",
    "Rheumatoid arthritis":     "EFO_0000685",
    "Asthma":                   "EFO_0000270",
    "Chronic kidney disease":   "EFO_0003884",
    "Heart failure":            "EFO_0003144",
}

PUBMED_QUERIES = [
    "drug repurposing gene disease network",
    "diabetes alzheimer shared genetic pathways",
    "metformin neuroprotective mechanism gene",
    "BRCA1 BRCA2 drug targets breast cancer",
    "insulin resistance neurodegeneration gene",
    "statin pleiotropic effects gene expression",
    "PCSK9 cardiovascular drug target",
    "GLP1 receptor agonist diabetes obesity gene",
    "TNF alpha inhibitor rheumatoid arthritis gene",
    "SGLT2 inhibitor heart failure kidney gene",
    "APOE alzheimer diabetes shared risk gene",
    "ACE inhibitor hypertension kidney protection mechanism",
    "drug gene interaction network pharmacogenomics",
    "multi-target drug discovery computational",
    "side effects drug gene pathway analysis"
]


def fetch_all_data():
    """Master function: fetch everything and save to disk."""
    print("=" * 60)
    print("  BioPharma GraphRAG — Data Collection")
    print("=" * 60)

    all_data = {
        "pubmed_articles": [],
        "gene_associations": [],
        "drug_associations": []
    }

    # 1. PubMed abstracts
    print("\n📚 Fetching PubMed abstracts...")
    for query in tqdm(PUBMED_QUERIES, desc="PubMed queries"):
        articles = fetch_pubmed_abstracts(query, max_results=30)
        all_data["pubmed_articles"].extend(articles)
        time.sleep(0.5)

    # Deduplicate by PMID
    seen = set()
    unique_articles = []
    for a in all_data["pubmed_articles"]:
        if a["pmid"] not in seen:
            seen.add(a["pmid"])
            unique_articles.append(a)
    all_data["pubmed_articles"] = unique_articles
    print(f"  Total unique articles: {len(unique_articles)}")

    # 2. Open Targets — gene associations
    print("\n🧬 Fetching gene-disease associations from Open Targets...")
    for disease_name, disease_id in tqdm(DISEASE_CATALOG.items(), desc="Diseases"):
        assocs = fetch_open_targets_associations(disease_id, disease_name, size=40)
        all_data["gene_associations"].extend(assocs)
        time.sleep(0.3)

    # 3. Open Targets — drug associations
    print("\n💊 Fetching drug-disease associations from Open Targets...")
    for disease_name, disease_id in tqdm(DISEASE_CATALOG.items(), desc="Drug lookups"):
        drugs = fetch_open_targets_drugs(disease_id, disease_name, size=25)
        all_data["drug_associations"].extend(drugs)
        time.sleep(0.3)

    # Save everything
    output_path = RAW_DATA_DIR / "biomedical_data.json"
    with open(output_path, "w") as f:
        json.dump(all_data, f, indent=2)

    print(f"\n✅ All data saved to {output_path}")
    print(f"   Articles:          {len(all_data['pubmed_articles'])}")
    print(f"   Gene associations: {len(all_data['gene_associations'])}")
    print(f"   Drug associations: {len(all_data['drug_associations'])}")

    return all_data


if __name__ == "__main__":
    fetch_all_data()
