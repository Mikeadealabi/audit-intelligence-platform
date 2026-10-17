from app.services.llm.schema import Inference, InvestigationResult, ObservedFact, ground_in_evidence


def _result(**kwargs) -> InvestigationResult:
    defaults = dict(
        summary="test",
        observed_facts=[],
        inferences=[],
        missing_checks=[],
        recommended_next_steps=[],
        uncertainties=[],
    )
    defaults.update(kwargs)
    return InvestigationResult(**defaults)


def test_fact_with_valid_evidence_id_kept():
    result = _result(observed_facts=[ObservedFact(text="duplicate pair", evidence_ids=["a", "b"])])
    grounded = ground_in_evidence(result, seen_evidence_ids={"a", "b"})
    assert len(grounded.observed_facts) == 1
    assert grounded.observed_facts[0].evidence_ids == ["a", "b"]


def test_fact_with_unseen_evidence_id_dropped_and_noted():
    result = _result(observed_facts=[ObservedFact(text="fabricated claim", evidence_ids=["never-returned"])])
    grounded = ground_in_evidence(result, seen_evidence_ids={"a", "b"})
    assert grounded.observed_facts == []
    assert any("1 claim" in u for u in grounded.uncertainties)


def test_fact_with_partial_evidence_ids_keeps_only_valid_subset():
    result = _result(observed_facts=[ObservedFact(text="mixed", evidence_ids=["a", "fabricated"])])
    grounded = ground_in_evidence(result, seen_evidence_ids={"a"})
    assert grounded.observed_facts[0].evidence_ids == ["a"]


def test_fact_with_no_evidence_ids_at_all_dropped():
    result = _result(observed_facts=[ObservedFact(text="bare assertion", evidence_ids=[])])
    grounded = ground_in_evidence(result, seen_evidence_ids={"a"})
    assert grounded.observed_facts == []


def test_inference_grounding_same_rules_as_facts():
    result = _result(
        inferences=[
            Inference(text="grounded", basis_evidence_ids=["a"], limitations="none"),
            Inference(text="ungrounded", basis_evidence_ids=["ghost"], limitations="none"),
        ]
    )
    grounded = ground_in_evidence(result, seen_evidence_ids={"a"})
    assert len(grounded.inferences) == 1
    assert grounded.inferences[0].text == "grounded"


def test_no_dropped_claims_means_no_extra_uncertainty_note():
    result = _result(observed_facts=[ObservedFact(text="fine", evidence_ids=["a"])], uncertainties=["pre-existing"])
    grounded = ground_in_evidence(result, seen_evidence_ids={"a"})
    assert grounded.uncertainties == ["pre-existing"]


def test_empty_result_passes_through_unchanged():
    result = _result(summary="nothing found")
    grounded = ground_in_evidence(result, seen_evidence_ids=set())
    assert grounded.summary == "nothing found"
    assert grounded.observed_facts == []
    assert grounded.uncertainties == []


def test_missing_checks_and_next_steps_untouched_by_grounding():
    result = _result(
        missing_checks=["no PO data available"],
        recommended_next_steps=[{"text": "ask the client", "requires_human_approval": True}],
    )
    grounded = ground_in_evidence(result, seen_evidence_ids=set())
    assert grounded.missing_checks == ["no PO data available"]
    assert len(grounded.recommended_next_steps) == 1
