"""Optional Amazon Bedrock layer for the Stage 21 evidence analyst.

The deterministic evidence analyst remains the source of truth. Bedrock may choose
which evidence tool to call and provide a supplementary explanation, but it never
replaces validated facts, provenance or limitations.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any, Iterable, Optional

from engine.analyst import EvidenceRecord, answer_evidence_question


_TRUE_VALUES = {"1", "true", "yes", "on"}
_THINKING_BLOCK = re.compile(r"<thinking>.*?</thinking>", re.IGNORECASE | re.DOTALL)
_RESPONSE_TAGS = re.compile(r"</?response>", re.IGNORECASE)


@dataclass(frozen=True)
class BedrockAnalystConfig:
    enabled: bool = False
    region: str = "eu-west-2"
    model_id: str = "amazon.nova-lite-v1:0"
    profile_name: Optional[str] = None
    max_tokens: int = 350

    @classmethod
    def from_env(cls) -> "BedrockAnalystConfig":
        enabled = os.getenv("RFS_BEDROCK_ENABLED", "").strip().lower() in _TRUE_VALUES
        profile = os.getenv("RFS_AWS_PROFILE") or os.getenv("AWS_PROFILE") or None
        try:
            max_tokens = int(os.getenv("RFS_BEDROCK_MAX_TOKENS", "350"))
        except ValueError:
            max_tokens = 350
        return cls(
            enabled=enabled,
            region=os.getenv("RFS_AWS_REGION", os.getenv("AWS_REGION", "eu-west-2")),
            model_id=os.getenv("RFS_BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            profile_name=profile,
            max_tokens=max(100, min(max_tokens, 1000)),
        )


def _build_client(config: BedrockAnalystConfig):
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - depends on deployment extras
        raise RuntimeError("boto3 is required when the Bedrock analyst is enabled") from exc

    kwargs = {"region_name": config.region}
    if config.profile_name:
        kwargs["profile_name"] = config.profile_name
    session = boto3.Session(**kwargs)
    return session.client("bedrock-runtime")


def _tool_config() -> dict[str, Any]:
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "search_studio_evidence",
                    "description": (
                        "Retrieve validated Renewable Flexibility Studio evidence, facts, "
                        "sources, formulas and limitations for a user question."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The evidence question to search for.",
                                }
                            },
                            "required": ["query"],
                        }
                    },
                }
            }
        ]
    }


def _validated_fact_lines(answer: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in answer.get("evidence", []):
        title = str(item.get("title", item.get("key", "Evidence")))
        for key, value in dict(item.get("facts", {})).items():
            lines.append(f"{title} | {key}: {value}")
    return lines


def _tool_payload(query: str, records: Iterable[EvidenceRecord]) -> dict[str, Any]:
    answer = answer_evidence_question(query, records)
    return {
        "question": answer["question"],
        "authoritative_answer": answer["answer"],
        "validated_facts": _validated_fact_lines(answer),
        "evidence": answer["evidence"],
        "sources": answer["sources"],
        "limitations": answer["limitations"],
        "formulas": answer["formulas"],
        "confidence": answer["confidence"],
    }


def _extract_text(message: dict[str, Any]) -> str:
    parts = [str(item["text"]) for item in message.get("content", []) if "text" in item]
    text = "\n".join(parts).strip()
    text = _THINKING_BLOCK.sub("", text)
    text = _RESPONSE_TAGS.sub("", text)
    return text.strip()


def answer_with_bedrock(
    question: str,
    records: Iterable[EvidenceRecord],
    *,
    config: Optional[BedrockAnalystConfig] = None,
    client: Any = None,
) -> dict[str, Any]:
    """Return deterministic evidence plus an optional Bedrock interpretation."""
    record_list = list(records)
    deterministic = answer_evidence_question(question, record_list)
    result = dict(deterministic)
    result.update(
        {
            "mode": "deterministic",
            "provider": None,
            "model_id": None,
            "ai_explanation": None,
            "tool_trace": [],
            "validated_facts": _validated_fact_lines(deterministic),
            "bedrock_error": None,
        }
    )
    if deterministic["confidence"] == "low":
        return result

    config = config or BedrockAnalystConfig.from_env()
    if client is None and not config.enabled:
        return result

    try:
        bedrock = client or _build_client(config)
        messages = [
            {
                "role": "user",
                "content": [{"text": question.strip()}],
            }
        ]
        first = bedrock.converse(
            modelId=config.model_id,
            system=[{
                "text": (
                    "You are the Renewable Flexibility Studio evidence copilot. "
                    "Use the search_studio_evidence tool before answering. "
                    "Do not answer from general knowledge when Studio evidence is available."
                )
            }],
            messages=messages,
            toolConfig=_tool_config(),
            inferenceConfig={"maxTokens": config.max_tokens, "temperature": 0},
        )
        assistant_message = first["output"]["message"]
        tool_uses = [item["toolUse"] for item in assistant_message.get("content", []) if "toolUse" in item]
        if not tool_uses:
            result["bedrock_error"] = "no_tool_requested"
            return result

        tool_use = tool_uses[0]
        if tool_use.get("name") != "search_studio_evidence":
            result["bedrock_error"] = "unsupported_tool_requested"
            return result

        tool_input = dict(tool_use.get("input", {}))
        tool_query = str(tool_input.get("query") or question)
        payload = _tool_payload(tool_query, record_list)
        messages.append(assistant_message)
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": tool_use["toolUseId"],
                            "content": [{"json": payload}],
                        }
                    }
                ],
            }
        )
        final = bedrock.converse(
            modelId=config.model_id,
            system=[{
                "text": (
                    "The tool result is authoritative. Never change, reverse or recalculate "
                    "validated facts. Keep the answer concise and focus on interpretation, "
                    "decision relevance and limitations. If facts are insufficient, say so."
                )
            }],
            messages=messages,
            toolConfig=_tool_config(),
            inferenceConfig={"maxTokens": config.max_tokens, "temperature": 0},
        )
        explanation = _extract_text(final["output"]["message"])
        if not explanation:
            result["bedrock_error"] = "empty_model_response"
            return result

        result.update(
            {
                "mode": "hybrid",
                "provider": "Amazon Bedrock",
                "model_id": config.model_id,
                "ai_explanation": explanation,
                "tool_trace": [
                    {
                        "tool": "search_studio_evidence",
                        "input": tool_input,
                        "confidence": payload["confidence"],
                    }
                ],
                "validated_facts": payload["validated_facts"],
            }
        )
        return result
    except Exception as exc:  # fallback must never break the Studio
        result["bedrock_error"] = type(exc).__name__
        return result
