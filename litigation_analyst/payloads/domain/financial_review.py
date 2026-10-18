"""Reconcile cited transaction records without treating accounting net as loss."""
import hashlib
import re
from decimal import Decimal

TYPES = {"requested", "approved", "posting", "reversal", "net_balance", "settlement"}
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?![\w.])")


def build(matter, documents, flagged):
    sources = {d.source_id: d for d in documents if d.source_id not in flagged}
    events, evidence, groups, seen = [], [], {}, {}
    for row in matter.get("financial_events", []):
        source = sources.get(row["source_id"])
        if source is None or source.text is None or source.text.count(row["quote"]) != 1:
            raise ValueError("Transaction event requires one unique quotation in an authorized readable source")
        amount = Decimal(row["amount"])
        amounts = {Decimal(m.group().replace(",", "")) for m in NUMBER.finditer(row["quote"])}
        if amount not in amounts or row["transaction_ref"] not in row["quote"]:
            raise ValueError("Transaction amount and reference must occur in the exact cited quotation")
        if row["event_type"] == "reversal" and amount > 0:
            raise ValueError("A reversal must carry its recorded non-positive signed amount")
        if row["currency"].casefold() not in row["quote"].casefold():
            raise ValueError("Transaction currency must be explicit in the cited quotation")
        start = source.text.index(row["quote"])
        end = start + len(row["quote"])
        key = (row["transaction_ref"], row["currency"], row["ledger_id"], row["record_id"])
        eid = hashlib.sha256(f"{source.source_id}|{source.content_sha256}|{start}|{end}".encode()).hexdigest()[:32]
        evidence.append({"evidence_id": eid, "source_id": source.source_id,
            "content_sha256": source.content_sha256, "start_offset": start, "end_offset": end,
            "text": row["quote"], "provenance_kind": "observed"})
        if key in seen:
            previous = seen[key]
            if any(previous.get(k) != row.get(k) for k in ("event_type", "amount", "event_date")):
                raise ValueError("Conflicting annotations for the same transaction record ID")
            previous["evidence_ids"] = list(dict.fromkeys(previous["evidence_ids"] + [eid]))
            continue
        event = {**row, "evidence_ids": [eid], "event_date": row.get("event_date"),
                 "date_basis": "ISO date in quoted record; timezone unresolved" if row.get("event_date") and row["event_date"] in row["quote"] else "Counsel annotation; verify source chronology" if row.get("event_date") else "Unresolved",
                 "classification_basis": "Counsel-labelled event; the unique quotation and number are verified, not its legal effect"}
        seen[key] = event
        events.append(event)
        group = groups.setdefault((row["transaction_ref"], row["currency"], row["ledger_id"]), [])
        group.append(event)
    transactions = []
    for (reference, currency, ledger), rows in groups.items():
        postings = [r for r in rows if r["event_type"] in {"posting", "reversal"}]
        net = sum((Decimal(r["amount"]) for r in postings), Decimal(0))
        recorded = [r["amount"] for r in rows if r["event_type"] == "net_balance"]
        approved = [r["amount"] for r in rows if r["event_type"] == "approved"]
        requested = [r["amount"] for r in rows if r["event_type"] == "requested"]
        difference = str(Decimal(requested[0]) - Decimal(approved[0])) if len(approved) == len(requested) == 1 else None
        transactions.append({"transaction_ref": reference, "currency": currency, "ledger_id": ledger,
            "posting_reversal_net": str(net) if postings else None, "recorded_net_values": recorded,
            "net_matches_recorded": all(net == Decimal(n) for n in recorded) if postings and recorded else None,
            "request_minus_approval": difference, "evidence_ids": list(dict.fromkeys(i for r in rows for i in r["evidence_ids"])),
            "qualification": "Arithmetic over the supplied, counsel-labelled records only. Duplicate content is not corroboration. Ledger net does not establish bank settlement, loss, intent or liability."})
    return {"events": events, "transactions": transactions, "evidence": list({r["evidence_id"]: r for r in evidence}.values()),
            "status": "Source-bound reconciliation" if events else "No counsel-labelled transaction records supplied"}
