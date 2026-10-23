"""Financial document inventory, extraction, and statement packet operations."""

from mn_sdk.integrations.block_inputs import save_declared_inputs
from mn_sdk.agent_events import activity_operation

from .common import *
from .state import read_state, save_result
from .source_ingestion import *

@activity_operation('Checking financial folders for changes', completed='Checking financial folders for changes: completed')
def step_financial_folder_watcher(block, inputs):
    from mn_blueprint_blocks.contracts import fingerprint
    from .state import finance_inputs, INPUT_KEYS
    from .knowledge import load_financial_knowledge
    block.check()
    request_identity = fingerprint({key: value for key, value in inputs["request"].items() if key in INPUT_KEYS})
    receipt_path = "financial/intake-receipt.json"
    if block.store.path(receipt_path).exists():
        previous = {"state": block.store.read_path(receipt_path)}
        saved = read_state(block, previous)
        if saved["request_identity"] != request_identity:
            raise ValueError("Financial intake request changed after capture")
        return {"status": "completed", **previous}
    selected = finance_inputs(block, inputs["request"])
    identity = {"request_identity": request_identity, "configuration": fingerprint(block.config)}
    started_path = "financial/intake-start.json"
    if block.store.path(started_path).exists():
        started = block.store.read_path(started_path)
        if any(started[key] != value for key, value in identity.items()):
            raise ValueError("Financial intake request changed during capture")
    else:
        started = {**identity, "created_at": utc_now_iso()}
        block.store.commit(started_path, started, kind="financial_intake_start")
    state = {**started, "inputs": selected, "workflow": {}, "actor_findings": {},
        "knowledge": load_financial_knowledge(),
        "input_artifact": save_declared_inputs(block, selected, runtime_file=__file__).to_dict()}
    files = []
    folder = Path(selected["document_folder"])
    for path in iter_input_files(folder):
        block.check()
        reference = block.store.commit_bytes("financial/sources/" + path.relative_to(folder).as_posix(), path.read_bytes(), kind="financial_source")
        files.append({"name": path.name, "artifact": reference.to_dict()})
    result = save_result(block, state, "financial_folder_watcher", {
        "document_folder": selected["document_folder"], "output_folder": str(block.output_directory),
        "files": files, "file_count": len(files), "monitoring": selected.get("monitoring") or {}, "ready": True})
    block.store.commit(receipt_path, result["state"], kind="financial_intake_receipt")
    return result

@activity_operation('Reading financial documents', completed='Reading financial documents: completed')
def step_financial_document_reader(block, inputs) -> dict[str, Any]:
    block.check()
    state = read_state(block, inputs["result"])
    ocr_client, ocr_status = build_ocr_runtime(block, state)
    docs = []
    for source in state["workflow"]["financial_folder_watcher"]["files"]:
        block.check()
        reference = source["artifact"]
        block.store.read_bytes(reference)
        docs.append(read_document(block.store.path(reference["path"]), ocr_client=ocr_client))
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc["kind"]] = counts.get(doc["kind"], 0) + 1
    return save_result(block, state, "financial_document_reader", {
        "documents": docs,
        "document_count": len(docs),
        "kind_counts": counts,
        "source_refs": [doc["source_ref"] for doc in docs],
        "warnings": list(ocr_status.get("warnings") or []) + [warning for doc in docs for warning in doc.get("warnings", [])],
        "ocr": ocr_status,
        "ocr_required_sources": [doc["source_ref"] for doc in docs if doc.get("ocr_required")],
        "ocr_required_count": len([doc for doc in docs if doc.get("ocr_required")]),
    })

@activity_operation('Extracting bank transactions', completed='Extracting bank transactions: completed')
def step_bank_statement_extractor(block, inputs) -> dict[str, Any]:
    block.check()
    state = read_state(block, inputs["previous"])
    docs = state["workflow"]["financial_document_reader"]["documents"]
    statements = [doc for doc in docs if doc["kind"] == "bank_statement"]
    extracted = []
    totals = {"deposits": 0.0, "withdrawals": 0.0, "fees": 0.0}
    opening_balance = 0.0
    closing_balance = 0.0
    for doc in statements:
        text = doc.get("text") or ""
        transactions = []
        statement_context = extract_statement_context(text)
        opening_balance = opening_balance or extract_named_amount(text, ["opening balance"])
        closing_balance = closing_balance or extract_named_amount(text, ["closing balance"])
        for line_no, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            amount = amount_from_line(line)
            if amount is None:
                continue
            if "deposit" in lowered or "payroll" in lowered:
                direction = "deposit"
                totals["deposits"] += amount
            elif "fee" in lowered:
                direction = "fee"
                totals["fees"] += amount
            elif "withdrawal" in lowered or "payment" in lowered or "rent" in lowered or "bill" in lowered:
                direction = "withdrawal"
                totals["withdrawals"] += amount
            else:
                continue
            classification = classify_cash_transaction(line.strip(), direction)
            transactions.append(
                {
                    "source_ref": doc["source_ref"],
                    "line_no": line_no,
                    "description": line.strip(),
                    "amount": amount,
                    "direction": direction,
                    **classification,
                }
            )
        extracted.append(
            {
                "source_ref": doc["source_ref"],
                "opening_balance": opening_balance,
                "closing_balance": closing_balance,
                **statement_context,
                "transactions": transactions,
            }
        )
    all_transactions = [item for statement in extracted for item in statement.get("transactions", [])]
    pending_classification_total = sum(
        float(item.get("amount") or 0.0)
        for item in all_transactions
        if item.get("classification_status") == "pending_customer_confirmation"
    )
    fee_total = float(totals.get("fees") or 0.0)
    fee_transactions = [item for item in all_transactions if item.get("direction") == "fee"]
    statement_periods = [statement.get("statement_period") for statement in extracted if statement.get("statement_period")]
    account_names = sorted({str(statement.get("account_name")) for statement in extracted if statement.get("account_name")})
    return save_result(block, state, "bank_statement_extractor", {
        "statement_count": len(statements),
        "statements": extracted,
        "totals": totals,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "net_cash_flow": totals["deposits"] - totals["withdrawals"] - totals["fees"],
        "statement_periods": statement_periods,
        "account_names": account_names,
        "account_coverage": "one_statement_and_one_account" if len(extracted) == 1 and len(account_names) <= 1 else "partial_or_multiple_accounts",
        "pending_classification_total": round(pending_classification_total, 2),
        "fee_review": {
            "fee_total": round(fee_total, 2),
            "fee_count": len(fee_transactions),
            "recurrence_status": "not_established" if fee_transactions else "not_detected",
            "annual_cost_if_monthly": round(fee_total * 12, 2) if fee_transactions else 0.0,
            "waiver_terms_status": "not_provided",
        },
        "warnings": [] if statements else ["no_bank_statement_detected"],
    })
