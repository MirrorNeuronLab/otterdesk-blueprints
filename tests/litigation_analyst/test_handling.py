"""Handling labels must gate both model extraction and published review material."""
# ruff: noqa: F811 -- Imported pytest fixtures are requested by parameter name.
import hashlib
import json

import pytest
from test_litigation_analyst import (  # noqa: F401 -- Module-local pytest fixtures.
    ScriptedModel,
    graph_engine_stub,
    make_context,
    modules,
)


@pytest.mark.parametrize("label", [
    "PRIVILEGED AND CONFIDENTIAL", "Attorney-Client Communication",
    "Attorney–Client Privileged", "ATTORNEY WORK-PRODUCT",
    "Legal Professional Privilege", "Seeking legal advice",
])
def test_common_labels_require_human_handling_review(modules, label):
    from domain.handling import potential_privilege
    assert potential_privilege(label + "\nCounsel review pending.")
    assert not potential_privilege("Confidential commercial pricing schedule.")


def test_initial_round_flags_the_actual_known_fact_case(modules, graph_engine_stub, tmp_path):
    from domain.round_state import initialize
    from test_litigation_analyst import BLUEPRINT
    context = make_context(tmp_path, BLUEPRINT / "examples/approval_reversal_case/inputs")
    modules["intake"].prepare_sources(context)
    modules["indexing"].build_indexes(context)
    result, _ = initialize(context)
    frozen = json.loads((context["run_dir"] / result["context"]["path"]).read_text())
    assert set(frozen["source_review_flags"]) == {"case:07_privileged_advice.txt"}


def test_hybrid_extraction_does_not_send_flagged_content(modules, tmp_path):
    from domain.intake import PreparedCorpus
    from domain.relationship_index import build
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "counsel.txt").write_text("Privileged and confidential. PRIVATE_EXTRACTION_SENTINEL")
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)
    context["config"]["source_relationships"]["mode"] = "hybrid"

    class NoModel:
        model = "fixture"
        def completion_text(self, *args):
            pytest.fail("Flagged source reached relationship model")

    result = build(context, PreparedCorpus(context["run_dir"] / "case", "case").scan(), llm_client=NoModel())
    assert result["model_calls"] == 0
    assert result["coverage"][0]["model_status"] == "excluded_handling_review"
    assert not result["complete"] and not result["proposals"]


def test_retained_flagged_passage_is_not_published(modules, graph_engine_stub, tmp_path):
    from unittest.mock import patch
    from domain.handling import review_flags
    from domain.intake import PreparedCorpus
    from mn_sdk_rag import EvidenceSpan
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.txt").write_text("Approval notice. Routine duties explain the correspondence.")
    sentinel = "PRIVATE_APPENDIX_SENTINEL"
    (folder / "counsel.txt").write_text("Privileged and confidential. " + sentinel)
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)
    modules["indexing"].build_indexes(context)
    root = context["run_dir"]
    case = root / "case"
    original = modules["research"].run_investigation
    def retained_evidence(*args, **kwargs):
        state, store = original(*args, **kwargs)
        documents = tuple(PreparedCorpus(case, "case").scan())
        state["data"]["source_review_flags"] = review_flags(documents)
        source = next(d for d in documents if d.source_id == "case:counsel.txt")
        identifier = hashlib.sha256(source.text.encode()).hexdigest()[:32]
        store.add_evidence(state["data"]["investigation_id"], EvidenceSpan(
            evidence_id=identifier, source_id=source.source_id, content_sha256=source.content_sha256,
            start_offset=0, end_offset=len(source.text), text=source.text, provenance_kind="observed"))
        return state, store
    with patch.object(modules["research"], "run_investigation", retained_evidence):
        modules["research"].investigate(context, llm_client=ScriptedModel())
    modules["reporting"].write_review(context)
    for name in ["final_report.md", "evidence_appendix.md", "graph_appendix.md", "case/workspace.json", "web/index.html"]:
        assert sentinel not in (root / name).read_text(), name
    assert sentinel in (case / "sources.json").read_text()  # Frozen audit remains intact.
