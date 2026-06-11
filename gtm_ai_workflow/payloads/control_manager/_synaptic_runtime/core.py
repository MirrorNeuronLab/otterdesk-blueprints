from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("mn.blueprint.gtm_ai")
    logger.setLevel(os.environ.get("MN_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    log_path = Path(os.environ.get("MN_BLUEPRINT_LOG_PATH", "/tmp/mn-business-email.log"))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=int(os.environ.get("MN_LOG_MAX_BYTES", "1048576")),
            backupCount=int(os.environ.get("MN_LOG_BACKUP_COUNT", "5")),
        )
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = configure_logging()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_plan(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [payload]
    fallback_plan: dict[str, Any] | None = None
    fallback_input: dict[str, Any] | None = None
    seen_ids: set[int] = set()

    while candidates:
        candidate = candidates.pop(0)
        if not isinstance(candidate, dict):
            continue
        marker = id(candidate)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)

        if isinstance(candidate.get("customer"), dict) and fallback_plan is None:
            fallback_plan = candidate

        sandbox_stdout = str(candidate.get("sandbox", {}).get("stdout") or "").strip()
        if sandbox_stdout:
            try:
                decoded = json.loads(sandbox_stdout)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                return get_plan(decoded)

        for key in ("body", "payload", "result", "message", "data"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)

        nested_input = candidate.get("input")
        if isinstance(nested_input, dict):
            if fallback_input is None:
                fallback_input = nested_input
            candidates.append(nested_input)

    return fallback_plan or fallback_input or payload


def load_input_plan() -> dict[str, Any]:
    payload = json.loads(Path(os.environ["MN_INPUT_FILE"]).read_text())
    return get_plan(payload)


def bundle_asset_dir(name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        candidate = parent / name
        if candidate.exists():
            return candidate
    return current.parents[2] / name


def bundle_input_dir() -> Path:
    return bundle_asset_dir("input")


def blueprint_root_dir() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "knowledge").is_dir():
            return parent
        if (parent / "config").is_dir() and (parent / "payloads").is_dir():
            return parent
    return current.parents[3]


def _read_input_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, dict) else {}


def read_business_context() -> str:
    return str(load_input_manifest().get("business_context", ""))


def read_email_rules() -> dict[str, Any]:
    return dict(load_input_manifest().get("email_rules", {})) or {
        "minimum_minutes_between_emails": 5
    }


def read_delivery_settings() -> dict[str, Any]:
    return dict(load_input_manifest().get("delivery", {}))


def read_crm_settings() -> dict[str, Any]:
    return dict(load_input_manifest().get("crm", {}))


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def crm_output_dir() -> Path:
    configured = (
        _env_first("GTM_CRM_CSV_DIR", "MN_CRM_CSV_DIR", "SYNAPTIC_CRM_CSV_DIR")
        or str(read_crm_settings().get("csv_folder", "")).strip()
        or "/tmp/mn_gtm_ai_workflow_crm"
    )
    path = Path(configured).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


CRM_FIELDS = [
    "account_id",
    "name",
    "email",
    "title",
    "company",
    "profile",
    "source",
    "stage",
    "status",
    "last_touch_at",
    "last_subject",
    "last_outreach_status",
    "last_delivery_recipient",
    "test_recipient_override",
    "response_summary",
    "likely_pain",
    "recommended_offer",
    "next_action",
    "insight_tags",
]


INSIGHT_FIELDS = [
    "timestamp",
    "account_id",
    "company",
    "title",
    "pain_signal",
    "response_signal",
    "positioning_insight",
    "recommended_product_feedback",
    "recommended_marketing_feedback",
    "source",
]


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _account_id(account: dict[str, Any]) -> str:
    return str(
        account.get("account_id")
        or account.get("customer_id")
        or account.get("id")
        or account.get("email")
        or account.get("name")
        or "unknown"
    ).strip()


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv_rows(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_safe(row.get(field, "")) for field in fields})


def upsert_crm_account(
    account: dict[str, Any],
    *,
    status: str,
    next_action: str = "",
    likely_pain: str = "",
    recommended_offer: str = "",
    response_summary: str = "",
    last_subject: str = "",
    last_outreach_status: str = "",
    last_delivery_recipient: str = "",
    test_recipient_override: bool = False,
    insight_tags: list[str] | str | None = None,
) -> dict[str, str]:
    path = crm_output_dir() / "crm.csv"
    rows = _read_csv_rows(path)
    account_id = _account_id(account)
    index = next(
        (
            idx
            for idx, row in enumerate(rows)
            if row.get("account_id") == account_id
            or (
                account.get("email")
                and row.get("email", "").lower() == str(account.get("email")).lower()
            )
        ),
        None,
    )
    existing = rows[index] if index is not None else {}
    tags = insight_tags if insight_tags is not None else existing.get("insight_tags", "")
    row = {
        **existing,
        "account_id": account_id,
        "name": _csv_safe(account.get("name") or existing.get("name")),
        "email": _csv_safe(account.get("email") or existing.get("email")),
        "title": _csv_safe(account.get("title") or account.get("job_title") or existing.get("title")),
        "company": _csv_safe(account.get("company") or existing.get("company")),
        "profile": _csv_safe(account.get("profile") or existing.get("profile")),
        "source": _csv_safe(account.get("source") or existing.get("source") or "seed"),
        "stage": _csv_safe(account.get("stage") or existing.get("stage") or "target"),
        "status": status or existing.get("status", ""),
        "last_touch_at": utc_now(),
        "last_subject": last_subject or existing.get("last_subject", ""),
        "last_outreach_status": last_outreach_status or existing.get("last_outreach_status", ""),
        "last_delivery_recipient": last_delivery_recipient
        or existing.get("last_delivery_recipient", ""),
        "test_recipient_override": str(bool(test_recipient_override)).lower()
        if test_recipient_override or not existing.get("test_recipient_override")
        else existing.get("test_recipient_override", ""),
        "response_summary": response_summary or existing.get("response_summary", ""),
        "likely_pain": likely_pain or existing.get("likely_pain", ""),
        "recommended_offer": recommended_offer or existing.get("recommended_offer", ""),
        "next_action": next_action or existing.get("next_action", ""),
        "insight_tags": _csv_safe(tags),
    }
    if index is None:
        rows.append(row)
    else:
        rows[index] = row
    _write_csv_rows(path, rows, CRM_FIELDS)
    return row


def append_market_insight(
    account: dict[str, Any],
    *,
    pain_signal: str = "",
    response_signal: str = "",
    positioning_insight: str = "",
    recommended_product_feedback: str = "",
    recommended_marketing_feedback: str = "",
    source: str = "gtm_ai_workflow",
) -> dict[str, str]:
    path = crm_output_dir() / "market_insights.csv"
    row = {
        "timestamp": utc_now(),
        "account_id": _account_id(account),
        "company": _csv_safe(account.get("company")),
        "title": _csv_safe(account.get("title") or account.get("job_title")),
        "pain_signal": pain_signal,
        "response_signal": response_signal,
        "positioning_insight": positioning_insight,
        "recommended_product_feedback": recommended_product_feedback,
        "recommended_marketing_feedback": recommended_marketing_feedback,
        "source": source,
    }
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INSIGHT_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    return row


def load_input_manifest() -> dict[str, Any]:
    input_dir = bundle_input_dir()
    manifest = _read_input_json(input_dir / "manifest.json")
    strategy = _read_input_json(input_dir / "strategy.json")
    knowledge = _read_input_json(blueprint_root_dir() / "knowledge" / "init" / "knowledge.json")
    if not knowledge:
        knowledge = _read_input_json(input_dir / "knowledge.json")
    merged = dict(manifest)
    if "business_context" in strategy:
        merged["business_context"] = strategy["business_context"]
    if "email_rules" in strategy:
        merged["email_rules"] = strategy["email_rules"]
    if "delivery" in strategy:
        merged["delivery"] = strategy["delivery"]
    if "crm" in strategy:
        merged["crm"] = strategy["crm"]
    for key in ("positioning", "funnel_strategy", "messaging_dna", "campaign_playbooks"):
        if key in strategy:
            merged[key] = strategy[key]
    merged_knowledge = dict(knowledge)
    campaign_playbooks = strategy.get("campaign_playbooks", {})
    if isinstance(campaign_playbooks, dict):
        merged_knowledge["campaign_playbooks"] = campaign_playbooks
    merged["knowledge"] = merged_knowledge
    return merged


def load_knowledge_section(section_name: str) -> dict[str, Any]:
    knowledge = load_input_manifest().get("knowledge", {})
    if not isinstance(knowledge, dict):
        return {}
    section = knowledge.get(section_name, {})
    return section if isinstance(section, dict) else {}


def load_template_library() -> dict[str, dict[str, Any]]:
    library: dict[str, dict[str, Any]] = {}
    templates_dir = bundle_input_dir() / "templates"
    if not templates_dir.exists():
        return library
    for path in sorted(templates_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        if isinstance(payload, dict) and payload.get("template_id"):
            library[str(payload["template_id"])] = payload
    return library


def db_connect() -> sqlite3.Connection:
    connection_string = os.environ.get("SYNAPTIC_DB_CONNECTION", "").strip()
    if connection_string:
        if not connection_string.startswith("sqlite:///"):
            raise RuntimeError(
                "Unsupported database connection string. Synaptic currently supports sqlite:///... only."
            )
        target = connection_string[len("sqlite:///") :]
    else:
        target = os.environ.get("SYNAPTIC_DB_PATH", "/tmp/mn_gtm_ai_workflow.db")
    conn = sqlite3.connect(target, timeout=30)
    conn.row_factory = sqlite3.Row
    ensure_db_schema(conn)
    return conn


def ensure_db_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_drafts (
            draft_id TEXT PRIMARY KEY,
            customer_id TEXT,
            runtime_job_id TEXT,
            status TEXT,
            subject TEXT,
            preview_text TEXT,
            body_text TEXT,
            html_body TEXT,
            scheduled_send_at TEXT,
            prepared_at TEXT,
            provider_id TEXT,
            sent_at TEXT,
            from_email TEXT,
            thread_message_id TEXT,
            in_reply_to_message_id TEXT,
            references_message_ids_json TEXT,
            source_payload_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_marketing_activity (
            activity_id TEXT PRIMARY KEY,
            customer_id TEXT,
            summary TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_logs (
            runtime_job_id TEXT,
            agent_id TEXT,
            level TEXT,
            message TEXT,
            details_json TEXT,
            created_at TEXT
        )
        """
    )
    seed_db_if_empty(conn)
    conn.commit()


def load_bootstrap_seed() -> dict[str, Any]:
    seed_path = bundle_input_dir() / "data" / "bootstrap_seed.json"
    if not seed_path.exists():
        return {}
    payload = json.loads(seed_path.read_text())
    return payload if isinstance(payload, dict) else {}


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"] if row is not None else 0)


def _source_payload_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _seed_draft_payload(draft: dict[str, Any]) -> dict[str, Any]:
    explicit = draft.get("draft")
    if isinstance(explicit, dict):
        return dict(explicit)
    payload = {
        "subject": draft.get("subject", ""),
        "preview_text": draft.get("preview_text", ""),
        "eyebrow": draft.get("eyebrow", ""),
        "headline": draft.get("headline", draft.get("subject", "")),
        "body_sections": draft.get("body_sections", []),
        "cta_label": draft.get("cta_label", "Review the GTM workflow"),
        "cta_url_slug": draft.get("cta_url_slug", "create"),
        "secondary_text": draft.get("secondary_text", ""),
        "footer_variant": draft.get("footer_variant", "default"),
        "signoff": draft.get("signoff", "Maya"),
    }
    return {key: value for key, value in payload.items() if value not in ("", [], None)}


def render_seed_draft_html(draft: dict[str, Any], source_payload: dict[str, Any]) -> str:
    html_body = str(draft.get("html_body") or "")
    if not draft.get("render_from_template"):
        return html_body
    try:
        from _synaptic_skills.marketing_email import build_design_slots, render_email_html

        draft_payload = _seed_draft_payload(draft)
        if not draft_payload:
            return html_body
        template_name = str(
            draft.get("template")
            or source_payload.get("design", {}).get("template")
            or "gtm_workflow_spotlight"
        )
        template = load_template_library().get(template_name)
        if not template:
            return html_body
        plan = dict(source_payload)
        plan.setdefault("campaign_type", source_payload.get("campaign_type", template_name))
        plan.setdefault("audience_segment", source_payload.get("audience_segment", "revenue_leaders"))
        plan["draft"] = draft_payload
        plan["design"] = {"template": template_name}
        slots = build_design_slots(plan=plan, brand=load_knowledge_section("brand"))
        return render_email_html(template, slots)
    except Exception:
        return html_body


def seed_db_if_empty(conn: sqlite3.Connection) -> None:
    if _table_count(conn, "email_drafts") or _table_count(conn, "customer_marketing_activity"):
        return

    seed = load_bootstrap_seed()
    if not seed:
        return

    for activity in seed.get("customer_marketing_activity", seed.get("activities", [])):
        if not isinstance(activity, dict):
            continue
        activity_id = str(activity.get("activity_id") or "").strip()
        customer_id = str(activity.get("customer_id") or "").strip()
        summary = str(activity.get("summary") or "").strip()
        if not activity_id or not customer_id or not summary:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO customer_marketing_activity (
                activity_id,
                customer_id,
                summary,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                activity_id,
                customer_id,
                summary,
                str(activity.get("created_at") or utc_now()),
            ),
        )

    for draft in seed.get("email_drafts", []):
        if not isinstance(draft, dict):
            continue
        draft_id = str(draft.get("draft_id") or "").strip()
        customer_id = str(draft.get("customer_id") or "").strip()
        if not draft_id or not customer_id:
            continue
        source_payload = _source_payload_dict(draft.get("source_payload_json", {}))
        draft_payload = _seed_draft_payload(draft)
        if draft_payload:
            source_payload.setdefault("draft", draft_payload)
        if draft.get("template"):
            source_payload.setdefault("design", {"template": str(draft["template"])})
        source_payload_json = json.dumps(source_payload or {}, sort_keys=True)
        html_body = render_seed_draft_html(draft, source_payload)
        references = draft.get("references_message_ids_json", "[]")
        if not isinstance(references, str):
            references = json.dumps(references or [], sort_keys=True)
        conn.execute(
            """
            INSERT OR IGNORE INTO email_drafts (
                draft_id,
                customer_id,
                runtime_job_id,
                status,
                subject,
                preview_text,
                body_text,
                html_body,
                scheduled_send_at,
                prepared_at,
                provider_id,
                sent_at,
                from_email,
                thread_message_id,
                in_reply_to_message_id,
                references_message_ids_json,
                source_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                customer_id,
                str(draft.get("runtime_job_id") or "seed"),
                str(draft.get("status") or "sent"),
                str(draft.get("subject") or ""),
                str(draft.get("preview_text") or ""),
                str(draft.get("body_text") or ""),
                html_body,
                str(draft.get("scheduled_send_at") or ""),
                str(draft.get("prepared_at") or ""),
                str(draft.get("provider_id") or ""),
                str(draft.get("sent_at") or ""),
                str(draft.get("from_email") or ""),
                str(draft.get("thread_message_id") or ""),
                str(draft.get("in_reply_to_message_id") or ""),
                references,
                source_payload_json,
            ),
        )


def recent_activities(customer_id: str, limit: int = 5) -> list[dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT summary, created_at
            FROM customer_marketing_activity
            WHERE customer_id = ?
            ORDER BY created_at DESC, activity_id DESC
            LIMIT ?
            """,
            (customer_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_sent_draft(customer_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM email_drafts
            WHERE customer_id = ? AND status = 'sent'
            ORDER BY sent_at DESC, prepared_at DESC
            LIMIT 1
            """,
            (customer_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def pending_ready_draft(customer_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM email_drafts
            WHERE customer_id = ? AND status = 'ready'
            ORDER BY prepared_at DESC
            LIMIT 1
            """,
            (customer_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def save_ready_draft(
    *,
    draft_id: str,
    customer_id: str,
    runtime_job_id: str | None,
    subject: str,
    preview_text: str,
    body_text: str,
    html_body: str,
    scheduled_send_at: str,
    source_payload: dict[str, Any],
) -> dict[str, Any]:
    prepared_at = utc_now()
    reply_context = dict(source_payload.get("reply_context") or {})
    references = list(reply_context.get("references_message_ids") or [])
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO email_drafts (
                draft_id,
                customer_id,
                runtime_job_id,
                status,
                subject,
                preview_text,
                body_text,
                html_body,
                scheduled_send_at,
                prepared_at,
                from_email,
                thread_message_id,
                in_reply_to_message_id,
                references_message_ids_json,
                source_payload_json
            ) VALUES (?, ?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                customer_id,
                runtime_job_id,
                subject,
                preview_text,
                body_text,
                html_body,
                scheduled_send_at,
                prepared_at,
                str(reply_context.get("reply_from_email") or ""),
                str(reply_context.get("thread_message_id") or ""),
                str(reply_context.get("in_reply_to_message_id") or ""),
                json.dumps(references, sort_keys=True),
                json.dumps(source_payload, sort_keys=True),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM email_drafts WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
    return dict(row)


def mark_draft_sent(draft_id: str, provider_id: str | None) -> dict[str, Any] | None:
    sent_at = utc_now()
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE email_drafts
            SET status = 'sent',
                provider_id = ?,
                sent_at = ?
            WHERE draft_id = ?
            """,
            (provider_id, sent_at, draft_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM email_drafts WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def add_marketing_activity(customer_id: str, summary: str) -> None:
    import uuid

    timestamp = utc_now().replace('-', '').replace(':', '').replace('+00:00', 'z').lower()
    activity_id = f"activity_{timestamp}_{uuid.uuid4().hex[:8]}"
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO customer_marketing_activity (
                activity_id,
                customer_id,
                summary,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (activity_id, customer_id, summary, utc_now()),
        )
        conn.commit()


def log_agent(
    runtime_job_id: str | None,
    agent_id: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    if not runtime_job_id:
        return
    logger.info("%s: %s", agent_id, message, extra={"details": details or {}})
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_logs (
                runtime_job_id,
                agent_id,
                level,
                message,
                details_json,
                created_at
            ) VALUES (?, ?, 'info', ?, ?, ?)
            """,
            (
                runtime_job_id,
                agent_id,
                message,
                json.dumps(details or {}, sort_keys=True),
                utc_now(),
            ),
        )
        conn.commit()


def completion_json(
    system_prompt: str, user_prompt: str, *, profile: str = "primary"
) -> dict[str, Any] | None:
    try:
        shared_skills_dir = bundle_asset_dir("_shared_skills")
        if str(shared_skills_dir) not in sys.path:
            sys.path.insert(0, str(shared_skills_dir))
        from mn_litellm_communicate_skill import completion_json as shared_completion_json
    except ImportError:
        return None

    try:
        return shared_completion_json(system_prompt, user_prompt)
    except Exception:
        return None
