from engine.analyst import EvidenceRecord
from engine.bedrock_analyst import BedrockAnalystConfig, answer_with_bedrock


def _records():
    return [
        EvidenceRecord(
            key="finance",
            title="Market-backed investment case",
            summary="Operating value is below lifecycle cost in the default screen.",
            facts={"CAPEX": "£25m", "NPV": "-£20.6m"},
            sources=("outputs/market_investment/market_investment_summary.json",),
            limitations=("Pre-feasibility only.",),
            keywords=("npv capex investment finance",),
        )
    ]


class FakeBedrockClient:
    def __init__(self):
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "tool-1",
                                    "name": "search_studio_evidence",
                                    "input": {"query": "Why is the NPV negative?"},
                                }
                            }
                        ],
                    }
                }
            }
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "text": (
                                "<thinking>private trace</thinking>"
                                "<response>The evidence indicates lifecycle cost remains "
                                "the main screening constraint, so the result should be "
                                "treated as pre-feasibility evidence.</response>"
                            )
                        }
                    ],
                }
            }
        }


class FailingBedrockClient:
    def converse(self, **kwargs):
        raise RuntimeError("simulated Bedrock outage")


def test_bedrock_layer_is_disabled_by_default():
    result = answer_with_bedrock(
        "Why is the NPV negative?",
        _records(),
        config=BedrockAnalystConfig(enabled=False),
    )
    assert result["mode"] == "deterministic"
    assert result["ai_explanation"] is None
    assert result["provider"] is None
    assert result["evidence"][0]["key"] == "finance"


def test_bedrock_tool_call_preserves_deterministic_evidence():
    client = FakeBedrockClient()
    result = answer_with_bedrock(
        "Why is the NPV negative?",
        _records(),
        config=BedrockAnalystConfig(enabled=True),
        client=client,
    )
    assert result["mode"] == "hybrid"
    assert result["provider"] == "Amazon Bedrock"
    assert result["evidence"][0]["key"] == "finance"
    assert "CAPEX" in result["validated_facts"][0]
    assert "<thinking>" not in result["ai_explanation"]
    assert result["tool_trace"][0]["tool"] == "search_studio_evidence"


def test_bedrock_failure_falls_back_without_losing_answer():
    result = answer_with_bedrock(
        "Why is the NPV negative?",
        _records(),
        config=BedrockAnalystConfig(enabled=True),
        client=FailingBedrockClient(),
    )
    assert result["mode"] == "deterministic"
    assert result["bedrock_error"] == "RuntimeError"
    assert "lifecycle cost" in result["answer"]
