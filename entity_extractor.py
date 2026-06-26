"""
entity_extractor.py — Extract biomedical entities and relationships using LLM.

Pulls out: DRUG, DISEASE, GENE, PROTEIN, PATHWAY, SIDE_EFFECT
And their relationships: TARGETS, TREATS, CAUSES, ASSOCIATED_WITH, etc.

Works with OpenAI API or Ollama (local).
"""
import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY, LLM_MODEL, OLLAMA_BASE_URL, ENTITY_TYPES, RELATION_TYPES


def get_llm_client():
    """Get OpenAI-compatible client (works with Ollama too)."""
    if OLLAMA_BASE_URL:
        return OpenAI(base_url=f"{OLLAMA_BASE_URL}/v1", api_key="ollama")
    return OpenAI(api_key=OPENAI_API_KEY)


EXTRACTION_PROMPT = """You are a biomedical entity and relationship extractor.

From the given text, extract:

ENTITIES (with type):
Types: {entity_types}

RELATIONSHIPS between entities:
Types: {relation_types}

Return ONLY valid JSON in this exact format, no other text:
{{
  "entities": [
    {{"name": "Metformin", "type": "DRUG", "aliases": ["metformin hydrochloride"]}},
    {{"name": "AMPK", "type": "GENE", "aliases": ["AMP-activated protein kinase", "PRKAA1"]}}
  ],
  "relationships": [
    {{
      "source": "Metformin",
      "target": "AMPK",
      "relation": "ACTIVATES",
      "evidence": "Metformin activates AMPK signaling pathway",
      "confidence": 0.9
    }}
  ]
}}

Rules:
- Normalize entity names (e.g., "type 2 diabetes mellitus" → "Type 2 Diabetes")
- Use official gene symbols when possible (e.g., TP53 not p53 protein)
- Include aliases for entities with multiple names
- Only extract relationships explicitly stated or strongly implied
- Confidence: 0.9+ for explicit statements, 0.7-0.9 for strong implications, 0.5-0.7 for weak implications
- Skip vague or generic entities (e.g., "the disease", "a drug")

TEXT:
{text}
"""


def extract_entities_from_text(text: str, source_id: str = "") -> dict:
    """
    Extract entities and relationships from a single text chunk.
    Returns dict with 'entities' and 'relationships' lists.
    """
    client = get_llm_client()

    prompt = EXTRACTION_PROMPT.format(
        entity_types=", ".join(ENTITY_TYPES),
        relation_types=", ".join(RELATION_TYPES),
        text=text[:3000]  # truncate to stay within token limits
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise biomedical NER system. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000
        )

        content = response.choices[0].message.content.strip()

        # Clean up markdown code fences if present
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        result = json.loads(content)

        # Tag each entity/relationship with source
        for ent in result.get("entities", []):
            ent["source_id"] = source_id
        for rel in result.get("relationships", []):
            rel["source_id"] = source_id

        return result

    except json.JSONDecodeError as e:
        print(f"  JSON parse error for {source_id}: {e}")
        return {"entities": [], "relationships": []}
    except Exception as e:
        print(f"  Extraction error for {source_id}: {e}")
        return {"entities": [], "relationships": []}


def extract_from_structured_data(gene_associations: list, drug_associations: list) -> dict:
    """
    Convert structured API data (Open Targets) directly into entities + relationships.
    No LLM needed — this is already structured!
    """
    entities = []
    relationships = []
    seen_entities = set()

    # Gene-Disease associations
    for assoc in gene_associations:
        disease = assoc["disease_name"]
        gene = assoc["gene_symbol"]
        gene_name = assoc.get("gene_name", "")
        score = assoc.get("association_score", 0)

        if disease not in seen_entities:
            entities.append({
                "name": disease, "type": "DISEASE",
                "aliases": [], "source_id": "open_targets"
            })
            seen_entities.add(disease)

        if gene and gene not in seen_entities:
            entities.append({
                "name": gene, "type": "GENE",
                "aliases": [gene_name] if gene_name else [],
                "source_id": "open_targets"
            })
            seen_entities.add(gene)

        if gene and score > 0.1:  # filter low-confidence
            relationships.append({
                "source": gene,
                "target": disease,
                "relation": "ASSOCIATED_WITH",
                "evidence": f"Open Targets association score: {score:.3f}",
                "confidence": min(score, 1.0),
                "source_id": "open_targets"
            })

    # Drug-Disease-Gene associations
    for drug_assoc in drug_associations:
        disease = drug_assoc["disease_name"]
        drug = drug_assoc["drug_name"]
        targets = drug_assoc.get("gene_targets", [])
        mechanism = drug_assoc.get("mechanism", "")
        phase = drug_assoc.get("phase", 0)

        if drug and drug not in seen_entities:
            entities.append({
                "name": drug, "type": "DRUG",
                "aliases": [], "source_id": "open_targets"
            })
            seen_entities.add(drug)

        # Drug → Disease (TREATS)
        if drug and disease:
            conf = min(0.5 + (phase or 0) * 0.1, 1.0)
            relationships.append({
                "source": drug,
                "target": disease,
                "relation": "TREATS",
                "evidence": f"Clinical phase {phase}. {mechanism}".strip(),
                "confidence": conf,
                "source_id": "open_targets"
            })

        # Drug → Gene (TARGETS)
        for gene in targets:
            if gene not in seen_entities:
                entities.append({
                    "name": gene, "type": "GENE",
                    "aliases": [], "source_id": "open_targets"
                })
                seen_entities.add(gene)

            relationships.append({
                "source": drug,
                "target": gene,
                "relation": "TARGETS",
                "evidence": mechanism or "Known drug target",
                "confidence": 0.85,
                "source_id": "open_targets"
            })

    return {"entities": entities, "relationships": relationships}


def merge_extractions(extractions: list[dict]) -> dict:
    """
    Merge multiple extraction results, deduplicating entities
    and consolidating relationships.
    """
    entity_map = {}  # name_lower -> entity
    all_relationships = []

    for extraction in extractions:
        for ent in extraction.get("entities", []):
            key = ent["name"].lower().strip()
            if key in entity_map:
                # Merge aliases
                existing = entity_map[key]
                new_aliases = set(existing.get("aliases", []))
                new_aliases.update(ent.get("aliases", []))
                existing["aliases"] = list(new_aliases)
            else:
                entity_map[key] = ent

        for rel in extraction.get("relationships", []):
            all_relationships.append(rel)

    # Deduplicate relationships (same source-target-relation)
    rel_map = {}
    for rel in all_relationships:
        key = (
            rel["source"].lower(),
            rel["target"].lower(),
            rel["relation"]
        )
        if key in rel_map:
            # Keep higher confidence
            if rel.get("confidence", 0) > rel_map[key].get("confidence", 0):
                rel_map[key] = rel
        else:
            rel_map[key] = rel

    return {
        "entities": list(entity_map.values()),
        "relationships": list(rel_map.values())
    }
