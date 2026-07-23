"""Tax routing, capture, workpaper, and review operations."""

from .common import *
from .knowledge import load_prompt
from .review_services import actor_review, review_artifact
from .source_ingestion import *

def step_tax_document_router(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    tax_docs = [
        doc
        for doc in docs
        if doc["kind"] in {"w2", "1099_int", "1099_r", "investment_tax_document", "tax_form_image", "tax_form_answer_file"}
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for doc in tax_docs:
        groups.setdefault(doc["kind"], []).append(
            {
                "source_ref": doc["source_ref"],
                "kind": doc["kind"],
                "text_preview": (doc.get("text") or "")[:500],
            }
        )
    missing = []
    if "w2" not in groups:
        missing.append("W-2")
    if not any(key.startswith("1099") for key in groups):
        missing.append("1099 evidence")
    return {
        "tax_year": ctx["payload"].get("tax_year"),
        "filing_status": ctx["payload"].get("filing_status"),
        "tax_document_count": len(tax_docs),
        "groups": groups,
        "missing_recommended_forms": missing,
        "warnings": ["draft_review_only_not_for_filing"],
    }

def step_tax_form_ocr_capturer(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    label_docs = {
        tax_form_stem(doc["source_ref"]): doc
        for doc in docs
        if doc.get("kind") == "tax_form_answer_file" and isinstance(doc.get("data"), dict)
    }
    image_docs = []
    seen_images: set[str] = set()
    for doc in docs:
        suffix = str(doc.get("suffix") or "").lower()
        stem = tax_form_stem(doc["source_ref"])
        if doc.get("kind") == "tax_form_image" or (suffix in {".png", ".jpg", ".jpeg", ".pdf"} and stem in label_docs):
            if doc["source_ref"] not in seen_images:
                image_docs.append(doc)
                seen_images.add(doc["source_ref"])

    forms: list[dict[str, Any]] = []
    warnings: list[str] = []
    matched_label_stems: set[str] = set()
    for image in image_docs:
        stem = tax_form_stem(image["source_ref"])
        label_doc = label_docs.get(stem)
        label_data = label_doc.get("data") if label_doc else {}
        form_type = tax_form_class_from_data(label_data) or "tax_form"
        captured_fields = structured_values_from_data(label_data, limit=24) if label_doc else []
        if form_type and not any(item.get("field") == "form_type" for item in captured_fields):
            captured_fields.insert(0, {"field": "form_type", "value": form_type})
        substantive_fields = substantive_tax_fields(captured_fields)
        image_warnings = list(image.get("warnings") or [])
        if label_doc:
            matched_label_stems.add(stem)
            validation_status = "matched_companion_answer_file"
            extraction_method = "image_metadata_plus_companion_answer_file"
        else:
            validation_status = "needs_manual_ocr_or_answer_file"
            extraction_method = "image_metadata_only"
            image_warnings.append("missing_companion_answer_file")
        if not substantive_fields:
            image_warnings.append("substantive_tax_fields_not_extracted")
        field_capture_status = "extracted" if substantive_fields else "identified_only"
        field_locations = [
            {
                "field": item.get("field"),
                "source_ref": image["source_ref"],
                "answer_file": label_doc["source_ref"] if label_doc else None,
                "location": "full_page_or_companion_label",
                "page": 1,
            }
            for item in captured_fields
        ]
        warnings.extend(image_warnings)
        forms.append(
            {
                "source_ref": image["source_ref"],
                "answer_file": label_doc["source_ref"] if label_doc else None,
                "form_type": form_type,
                "ocr_required": True,
                "extraction_method": extraction_method,
                "captured_fields": captured_fields,
                "substantive_fields": substantive_fields,
                "substantive_field_count": len(substantive_fields),
                "field_capture_status": field_capture_status,
                "readiness_status": TAX_READINESS_LABELS[field_capture_status],
                "field_locations": field_locations,
                "validation_status": validation_status,
                "confidence": 0.82 if label_doc else 0.48,
                "warnings": image_warnings,
            }
        )

    for stem, label_doc in label_docs.items():
        if stem in matched_label_stems:
            continue
        label_data = label_doc.get("data") or {}
        form_type = tax_form_class_from_data(label_data) or "tax_form"
        captured_fields = structured_values_from_data(label_data, limit=24)
        if form_type and not any(item.get("field") == "form_type" for item in captured_fields):
            captured_fields.insert(0, {"field": "form_type", "value": form_type})
        substantive_fields = substantive_tax_fields(captured_fields)
        warnings.append("answer_file_without_matching_source_image")
        if not substantive_fields:
            warnings.append("substantive_tax_fields_not_extracted")
        forms.append(
            {
                "source_ref": label_doc["source_ref"],
                "answer_file": label_doc["source_ref"],
                "form_type": form_type,
                "ocr_required": False,
                "extraction_method": "companion_answer_file_only",
                "captured_fields": captured_fields,
                "substantive_fields": substantive_fields,
                "substantive_field_count": len(substantive_fields),
                "field_capture_status": "extracted" if substantive_fields else "identified_only",
                "readiness_status": TAX_READINESS_LABELS["extracted" if substantive_fields else "identified_only"],
                "field_locations": [],
                "validation_status": "needs_source_image_review",
                "confidence": 0.62,
                "warnings": ["answer_file_without_matching_source_image"],
            }
        )

    review_required = [
        form["source_ref"]
        for form in forms
        if form["validation_status"] != "matched_companion_answer_file"
        or form.get("warnings")
        or not form.get("substantive_field_count")
    ]
    incomplete_sources = [
        form["source_ref"]
        for form in forms
        if not form.get("substantive_field_count")
    ]
    return {
        "tax_form_count": len(forms),
        "answer_file_count": len(label_docs),
        "ocr_required_count": len([form for form in forms if form.get("ocr_required")]),
        "forms": forms,
        "review_required_sources": review_required,
        "substantive_field_count": sum(int(form.get("substantive_field_count") or 0) for form in forms),
        "incomplete_sources": incomplete_sources,
        "readiness_status": "incomplete" if incomplete_sources or review_required else "extracted_pending_reconciliation",
        "status_definitions": {
            "identified": "Form type or image presence recognized.",
            "extracted": "One or more substantive tax fields were captured.",
            "reconciled": "Captured fields agree with the source image and supplied records.",
            "complete": "All expected forms and substantive fields are present and reconciled.",
        },
        "warnings": sorted(set(warnings)),
        "review_only": True,
        "recommended_action": "review_captured_tax_form_fields_against_source_images_before_tax_use",
    }

def step_tax_workpaper_preparer(ctx: dict[str, Any]) -> dict[str, Any]:
    router = ctx["state"]["workflow"]["tax_document_router"]
    tax_capture = ctx["state"]["workflow"]["tax_form_ocr_capturer"]
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    wages = 0.0
    withholding = 0.0
    interest = 0.0
    retirement_distribution = 0.0
    for doc in docs:
        text = doc.get("text") or ""
        kind = doc["kind"]
        if kind == "w2":
            wages += extract_named_amount(text, ["box 1 wages", "wages"])
            withholding += extract_named_amount(text, ["box 2 federal income tax withheld", "federal income tax withheld"])
        elif kind == "1099_int":
            interest += extract_named_amount(text, ["box 1 interest income", "interest income"])
            withholding += extract_named_amount(text, ["box 4 federal income tax withheld", "federal income tax withheld"])
        elif kind == "1099_r":
            retirement_distribution += extract_named_amount(text, ["taxable amount", "gross distribution"])
            withholding += extract_named_amount(text, ["box 4 federal income tax withheld", "federal income tax withheld"])
    draft_income = wages + interest + retirement_distribution
    findings = actor_review(
        ctx["config"],
        ctx["llm"],
        "tax_workpaper_preparer",
        "Draft tax workpapers prepared for human review.",
        {
            "deterministic_workpaper_totals": {
                "wages": wages,
                "interest_income": interest,
                "retirement_distributions": retirement_distribution,
                "draft_income_total": draft_income,
                "federal_withholding": withholding,
            },
            "routed_tax_documents": router,
            "tax_form_ocr_capture": tax_capture,
            "review_constraints": [
                "Do not change draft tax totals.",
                "Do not mark anything filing-ready.",
                "Only identify completeness issues, source-review needs, and manager-review questions.",
            ],
        },
        prompt_details=load_prompt("tax-llm-review.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    blockers = list(router.get("missing_recommended_forms") or [])
    if tax_capture.get("review_required_sources"):
        blockers.append("Tax form OCR capture requires source-image review")
    for source_ref in tax_capture.get("incomplete_sources") or []:
        blockers.append(f"Substantive tax fields were not extracted from {source_ref}")
    if draft_income <= 0:
        blockers.append("No taxable-income source values detected")
    included_sources = [
        doc["source_ref"]
        for doc in docs
        if doc.get("kind") in {"w2", "1099_int", "1099_r"}
    ]
    excluded_form_types = sorted({
        str(form.get("form_type"))
        for form in tax_capture.get("forms", [])
        if not form.get("substantive_field_count") and form.get("form_type")
    })
    blockers = list(dict.fromkeys(blockers))
    return {
        "tax_year": router.get("tax_year"),
        "filing_status": router.get("filing_status"),
        "workpapers": {
          "wages": wages,
          "interest_income": interest,
          "retirement_distributions": retirement_distribution,
          "draft_income_total": draft_income,
          "federal_withholding": withholding,
          "included_source_refs": included_sources,
          "excluded_form_types": excluded_form_types,
          "coverage_status": "incomplete" if excluded_form_types or blockers else "complete",
          "draft_income_scope": "W-2, 1099-INT, and 1099-R text fields only; unextracted forms are excluded",
        },
        "manager_review": {
            "required": True,
            "blockers": blockers,
            "review_only": True
        },
        "tax_form_ocr_capture": {
            "tax_form_count": tax_capture.get("tax_form_count", 0),
            "answer_file_count": tax_capture.get("answer_file_count", 0),
            "review_required_sources": tax_capture.get("review_required_sources", []),
            "incomplete_sources": tax_capture.get("incomplete_sources", []),
            "readiness_status": tax_capture.get("readiness_status"),
        },
        "readiness_status": "incomplete" if blockers else "review_required",
        "actor_finding": findings,
        "warnings": ["draft_tax_packet_not_ready_to_file"],
    }

def step_tax_llm_reviewer(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    router = workflow["tax_document_router"]
    tax_capture = workflow["tax_form_ocr_capturer"]
    workpaper = workflow["tax_workpaper_preparer"]
    source_refs = sorted(
        {
            str(item.get("source_ref"))
            for docs in router.get("groups", {}).values()
            for item in docs
            if item.get("source_ref")
        }
        | {
            str(form.get("source_ref"))
            for form in tax_capture.get("forms", [])
            if form.get("source_ref")
        }
    )
    blockers = list(workpaper.get("manager_review", {}).get("blockers") or [])
    evidence_gaps = [f"Missing recommended tax evidence: {item}" for item in router.get("missing_recommended_forms", [])]
    if tax_capture.get("review_required_sources"):
        evidence_gaps.append("One or more OCR/answer-file packets require source-image review.")
    for source_ref in tax_capture.get("incomplete_sources") or []:
        evidence_gaps.append(
            f"{source_ref} was identified, but no substantive tax fields were extracted; any draft income total may be incomplete."
        )
    if workpaper.get("workpapers", {}).get("draft_income_total", 0) <= 0:
        evidence_gaps.append("Draft income total is zero or unavailable in deterministic tax workpapers.")
    return review_artifact(
        ctx,
        step_id="tax_llm_reviewer",
        summary="Tax LLM reviewer checked draft workpapers, OCR capture, missing-form blockers, and filing-boundary constraints.",
        context={
            "tax_document_router": router,
            "tax_form_ocr_capturer": tax_capture,
            "tax_workpaper_preparer": workpaper,
            "review_constraints": [
                "Do not change wages, interest, distributions, withholding, or draft-income totals.",
                "Do not give legal/tax filing advice.",
                "Do not mark OCR capture as filing-ready.",
            ],
        },
        source_refs=source_refs,
        key_findings=[
            f"Draft tax income total is {money(workpaper.get('workpapers', {}).get('draft_income_total'))}.",
            f"{tax_capture.get('tax_form_count', 0)} tax-form image/answer packet(s) were identified; {tax_capture.get('substantive_field_count', 0)} substantive field(s) were captured.",
        ],
        review_questions=[
            "Are the routed tax documents complete for the taxpayer's situation?",
            "Have OCR captured fields been checked against source images and companion answer files?",
            "Should any manager blockers remain before tax-preparation downstream use?",
        ],
        evidence_gaps=evidence_gaps,
        risk_flags=blockers + list(tax_capture.get("warnings") or []),
        next_steps=[
            "Review missing-form and OCR blockers with a qualified human reviewer.",
            "Reconcile draft tax totals to source forms before any tax filing workflow.",
        ],
    )

__all__ = ["step_tax_document_router", "step_tax_form_ocr_capturer", "step_tax_llm_reviewer", "step_tax_workpaper_preparer"]
