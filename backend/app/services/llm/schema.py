from pydantic import BaseModel, Field

# Kept in sync by hand with the Pydantic models below — see test_llm_schema.py for a
# round-trip check. This is what's sent as output_config.format to force Claude's
# final answer into this exact shape (see docs/claude-tool-contract.md).
INVESTIGATION_RESULT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "observed_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "inferences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "basis_evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "limitations": {"type": "string"},
                },
                "required": ["text", "basis_evidence_ids", "limitations"],
                "additionalProperties": False,
            },
        },
        "missing_checks": {"type": "array", "items": {"type": "string"}},
        "recommended_next_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "requires_human_approval": {"type": "boolean"},
                },
                "required": ["text", "requires_human_approval"],
                "additionalProperties": False,
            },
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "observed_facts",
        "inferences",
        "missing_checks",
        "recommended_next_steps",
        "uncertainties",
    ],
    "additionalProperties": False,
}


class ObservedFact(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class Inference(BaseModel):
    text: str
    basis_evidence_ids: list[str] = Field(default_factory=list)
    limitations: str = ""


class RecommendedNextStep(BaseModel):
    text: str
    requires_human_approval: bool = True


class InvestigationResult(BaseModel):
    summary: str
    observed_facts: list[ObservedFact] = Field(default_factory=list)
    inferences: list[Inference] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    recommended_next_steps: list[RecommendedNextStep] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


def ground_in_evidence(result: InvestigationResult, seen_evidence_ids: set[str]) -> InvestigationResult:
    """Drops any observed_fact/inference whose evidence IDs weren't actually
    returned by a tool call during this investigation run, and records how many
    were dropped. This is the server-side enforcement of "no claim without
    evidence" — the model's self-reported citations are never trusted as-is."""
    dropped = 0
    grounded_facts: list[ObservedFact] = []
    for fact in result.observed_facts:
        valid_ids = [eid for eid in fact.evidence_ids if eid in seen_evidence_ids]
        if not valid_ids:
            dropped += 1
            continue
        grounded_facts.append(ObservedFact(text=fact.text, evidence_ids=valid_ids))

    grounded_inferences: list[Inference] = []
    for inference in result.inferences:
        valid_ids = [eid for eid in inference.basis_evidence_ids if eid in seen_evidence_ids]
        if not valid_ids:
            dropped += 1
            continue
        grounded_inferences.append(
            Inference(text=inference.text, basis_evidence_ids=valid_ids, limitations=inference.limitations)
        )

    uncertainties = list(result.uncertainties)
    if dropped:
        uncertainties.append(
            f"{dropped} claim(s) were removed because they cited evidence not returned by any "
            f"tool call during this investigation and could not be verified."
        )

    return InvestigationResult(
        summary=result.summary,
        observed_facts=grounded_facts,
        inferences=grounded_inferences,
        missing_checks=result.missing_checks,
        recommended_next_steps=result.recommended_next_steps,
        uncertainties=uncertainties,
    )
