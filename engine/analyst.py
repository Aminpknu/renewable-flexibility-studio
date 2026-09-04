"""Stage 21 explainable evidence analyst.

The first release is deliberately retrieval-grounded and deterministic. It accepts
natural-language questions, ranks curated evidence records, and returns the facts,
sources and limitations that support the answer. It does not call an external LLM
or invent facts beyond the supplied evidence registry.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


@dataclass(frozen=True)
class EvidenceRecord:
    key: str
    title: str
    summary: str
    facts: dict[str, Any]
    sources: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    formulas: tuple[str, ...] = ()

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are",
    "was", "were", "be", "this", "that", "it", "my", "me", "show", "tell",
    "what", "why", "how", "which", "does", "do", "did", "about", "with",
}

_SYNONYMS = {
    "battery": {"bess", "storage", "soc", "mwh", "mw"},
    "degradation": {"wear", "soh", "cycle", "cycling", "health", "lifetime"},
    "finance": {"npv", "bcr", "irr", "dscr", "llcr", "capex", "opex", "debt"},
    "forecast": {"p10", "p50", "p90", "uncertainty", "probabilistic", "quantile"},
    "market": {"wholesale", "price", "arbitrage", "dispatch", "value"},
    "bm": {"balancing", "mechanism", "bid", "offer", "boa", "activation"},
    "ancillary": {"reserve", "quick", "slow", "dynamic", "acceptance", "service"},
    "source": {"reference", "evidence", "data", "provenance", "origin"},
    "spatial": {"zone", "city", "demand", "net", "load", "location"},
}


def _tokens(text: str) -> set[str]:
    raw = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in _STOPWORDS}
    expanded = set(raw)
    for canonical, related in _SYNONYMS.items():
        family = {canonical, *related}
        if raw.intersection(family):
            expanded.update(family)
    return expanded


def rank_evidence(question: str, records: Iterable[EvidenceRecord]) -> list[tuple[float, EvidenceRecord]]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Analyst question cannot be empty.")
    query = _tokens(question)
    ranked: list[tuple[float, EvidenceRecord]] = []
    for record in records:
        title_tokens = _tokens(record.title)
        keyword_tokens = _tokens(" ".join(record.keywords))
        summary_tokens = _tokens(record.summary)
        fact_tokens = _tokens(" ".join([*record.facts.keys(), *(str(v) for v in record.facts.values())]))
        score = (
            4.0 * len(query & title_tokens)
            + 3.0 * len(query & keyword_tokens)
            + 1.5 * len(query & fact_tokens)
            + 1.0 * len(query & summary_tokens)
        )
        if record.key.lower() in question.lower():
            score += 5.0
        ranked.append((score, record))
    return sorted(ranked, key=lambda item: (-item[0], item[1].title))


def answer_evidence_question(
    question: str,
    records: Iterable[EvidenceRecord],
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    ranked = rank_evidence(question, records)
    if not ranked:
        raise ValueError("Evidence registry is empty.")
    best_score = ranked[0][0]
    if best_score <= 0:
        return {
            "question": question.strip(),
            "answer": "I could not find a strong evidence match in the Studio registry. Try asking about forecasts, battery/SOH, wholesale/BM, ancillary services, investment/finance, spatial zones, assumptions or sources.",
            "confidence": "low",
            "evidence": [],
            "sources": [],
            "limitations": ["No external web or generative model was used to fill the evidence gap."],
            "formulas": [],
        }
    qlower = question.lower()
    compare = any(word in qlower for word in ("compare", "versus", " vs ", "difference"))
    source_intent = any(word in qlower for word in ("source", "reference", "where", "provenance"))
    formula_intent = any(word in qlower for word in ("formula", "equation", "calculate", "calculation"))
    selected_count = 2 if compare else max(1, min(top_k, 3))
    selected = [record for score, record in ranked[:selected_count] if score > 0]
    primary = selected[0]

    answer_parts = [primary.summary]
    if primary.facts:
        facts = "; ".join(f"{key}: {value}" for key, value in primary.facts.items())
        answer_parts.append(f"Key evidence: {facts}.")
    if compare and len(selected) > 1:
        secondary = selected[1]
        secondary_facts = "; ".join(f"{key}: {value}" for key, value in secondary.facts.items())
        answer_parts.append(f"Comparison evidence from {secondary.title}: {secondary.summary} Key evidence: {secondary_facts}.")
    if source_intent:
        answer_parts.append("The source list below is the provenance used for this answer.")
    if formula_intent and primary.formulas:
        answer_parts.append("The relevant formulation is included below.")

    sources = list(dict.fromkeys(source for r in selected for source in r.sources))
    limitations = list(dict.fromkeys(limit for r in selected for limit in r.limitations))
    formulas = list(dict.fromkeys(formula for r in selected for formula in r.formulas)) if formula_intent else []
    confidence = "high" if best_score >= 10 else "medium" if best_score >= 4 else "low"
    return {
        "question": question.strip(),
        "answer": " ".join(answer_parts),
        "confidence": confidence,
        "evidence": [{"key": r.key, "title": r.title, "facts": dict(r.facts)} for r in selected],
        "sources": sources,
        "limitations": limitations,
        "formulas": formulas,
    }
