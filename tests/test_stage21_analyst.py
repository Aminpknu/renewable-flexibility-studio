from engine.analyst import EvidenceRecord, answer_evidence_question, rank_evidence


def _records():
    return [
        EvidenceRecord(
            key="forecast", title="Stage 14 probabilistic forecast",
            summary="P10/P50/P90 uncertainty is calibrated from prior V2 residual evidence.",
            facts={"coverage": "80.8% locked mixed"},
            sources=("outputs/probabilistic/stage14_summary.json",),
            limitations=("Not an ECMWF ensemble forecast.",),
            keywords=("forecast uncertainty p10 p50 p90 quantile",),
            formulas=("Pq = forecast + conditional residual quantile",),
        ),
        EvidenceRecord(
            key="finance", title="Project finance screen",
            summary="The default screening case has negative NPV because operating value is below lifecycle cost.",
            facts={"CAPEX": "£25m", "NPV": "negative"},
            sources=("outputs/project_finance/project_finance_summary.json",),
            limitations=("Pre-feasibility only.",),
            keywords=("npv capex debt dscr finance",),
        ),
    ]


def test_analyst_ranks_relevant_evidence_and_preserves_sources():
    ranked = rank_evidence("Why is the NPV negative and what CAPEX is assumed?", _records())
    assert ranked[0][1].key == "finance"
    answer = answer_evidence_question("Why is the NPV negative and what is the source?", _records())
    assert answer["evidence"][0]["key"] == "finance"
    assert "project_finance_summary.json" in answer["sources"][0]
    assert answer["confidence"] in {"medium", "high"}


def test_analyst_returns_formula_only_when_requested():
    answer = answer_evidence_question("How is P10 forecast uncertainty calculated?", _records())
    assert answer["evidence"][0]["key"] == "forecast"
    assert answer["formulas"]


def test_analyst_does_not_invent_for_unknown_question():
    answer = answer_evidence_question("Tell me about lunar mining economics", _records())
    assert answer["confidence"] == "low"
    assert answer["evidence"] == []
    assert "No external web" in answer["limitations"][0]
