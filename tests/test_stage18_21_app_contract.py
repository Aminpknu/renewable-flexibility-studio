from pathlib import Path

import app


def test_stages_18_to_21_are_exposed_in_layout():
    layout = str(app.app.layout)
    for component_id in (
        "asset-store", "asset-select", "degradation-store", "degradation-summary",
        "stochastic-store", "stoch-run", "analyst-question", "analyst-answer",
    ):
        assert component_id in layout


def test_stage20_uses_stage19_wear_store_and_stage21_is_grounded():
    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "marginal_wear_cost_gbp_per_mwh_throughput" in source
    assert "answer_evidence_question" in source
    assert "not an external generative large language model (LLM)" in source
