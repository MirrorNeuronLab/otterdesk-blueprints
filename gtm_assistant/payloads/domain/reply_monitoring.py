from __future__ import annotations

import hashlib
import imaplib
import json
import os
import signal
import threading
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Callable, Mapping

from mn_sdk.blueprint_support.workflow_state import write_json

from .delivery import (
    DELIVERY_RECEIPT_PATH,
    SMTP_DEV_RECIPIENT_ENV,
    SMTP_PASSWORD_ENV,
    SMTP_USERNAME_ENV,
    deliver_approved_development_email,
    development_email_approval_request_id,
    development_email_approval_response,
)


DEVELOPMENT_REPLY_MONITORING_STATE_PATH = "development_reply_monitoring_state.json"
ICLOUD_IMAP_HOST = "imap.mail.me.com"
ICLOUD_IMAP_PORT = 993
_MAX_POLL_INTERVAL_SECONDS = 300.0
_MIN_POLL_INTERVAL_SECONDS = 5.0
_MAX_REPLY_FINGERPRINTS = 200
_ImapFactory = Callable[..., Any]


def monitor_development_email_replies(context: dict[str, Any], **_: Any) -> dict[str, Any]:
    """Run the read-only reply monitor until the service is manually stopped."""

    settings = _settings(context)
    config = context.get("config") if isinstance(context.get("config"), Mapping) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), Mapping) else {}
    if bool(execution.get("quick_test", False)):
        return _not_started(context, "quick_test")
    delivery = _delivery_receipt(context)
    if delivery.get("status") not in {"sent", "already_sent"} and _smtp_delivery_enabled(context):
        return _await_approved_delivery(context, settings, "approved_development_delivery_not_found")
    if not bool(settings.get("enabled", False)):
        return _not_started(context, "reply_monitoring_disabled")
    if delivery.get("status") not in {"sent", "already_sent"}:
        return _await_approved_delivery(context, settings, "approved_development_delivery_not_found")
    outbound_message_id = str(delivery.get("message_id") or "").strip()
    if not outbound_message_id:
        return _await_approved_delivery(context, settings, "development_delivery_message_id_not_found")

    environment = os.environ
    username = str(environment.get(SMTP_USERNAME_ENV) or "").strip()
    password = str(environment.get(SMTP_PASSWORD_ENV) or "")
    development_recipient = str(environment.get(SMTP_DEV_RECIPIENT_ENV) or "").strip()
    if not username or not password or not development_recipient:
        raise RuntimeError(
            "Reply monitoring requires the development SMTP identity and recipient through the worker environment"
        )

    from mn_prototype_supervised_service_agent import (
        ServiceContext,
        SupervisedServiceSpec,
        create_agent as create_supervised_service,
    )

    service = create_supervised_service(
        SupervisedServiceSpec(
            serve=lambda _service_context: _monitor_forever(
                context,
                settings=settings,
                username=username,
                password=password,
                development_recipient=development_recipient,
                outbound_message_id=outbound_message_id,
            )
        )
    )
    service(
        context=ServiceContext(
            config=context["config"],
            run_dir=Path(context["run_dir"]),
            output_folder=Path(context.get("output_folder") or context["run_dir"]),
        )
    )
    return _result_from_state(context)


def _await_approved_delivery(
    context: dict[str, Any], settings: Mapping[str, Any], reason: str
) -> dict[str, Any]:
    """Keep the service inspectable while an approval-gated send has not happened."""

    from mn_prototype_supervised_service_agent import (
        ServiceContext,
        SupervisedServiceSpec,
        create_agent as create_supervised_service,
    )

    service = create_supervised_service(
        SupervisedServiceSpec(
            serve=lambda _service_context: _wait_for_approved_delivery(
                context,
                settings=settings,
                reason=reason,
            )
        )
    )
    service(
        context=ServiceContext(
            config=context["config"],
            run_dir=Path(context["run_dir"]),
            output_folder=Path(context.get("output_folder") or context["run_dir"]),
        )
    )
    return _result_from_state(context)


def _deliver_after_human_approval(context: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(str(context["run_dir"]))
    interventions_artifact = _json_object(run_dir / "draft_customer_interventions.json")
    interventions = interventions_artifact.get("interventions")
    if not isinstance(interventions, list) or not interventions:
        raise RuntimeError("Approved development delivery requires the reviewed intervention artifact")
    run_id = str(context.get("run_id") or context.get("job_id") or "").strip()
    approved_context = {
        **context,
        "payload": {
            **(context.get("payload") if isinstance(context.get("payload"), dict) else {}),
            "email_send_approval": {
                "approved": True,
                "approval_id": development_email_approval_request_id(run_id),
            },
        },
    }
    delivery = deliver_approved_development_email(approved_context, interventions)
    if delivery.get("status") not in {"sent", "already_sent"}:
        raise RuntimeError("Approved development email was not sent")
    return delivery


def _wait_for_approved_delivery(
    context: dict[str, Any], *, settings: Mapping[str, Any], reason: str
) -> dict[str, Any]:
    state = _load_state(context)
    stop_requested = threading.Event()
    previous_handlers = _install_stop_handlers(stop_requested)
    stop_file = _stop_file(context, settings)
    interval_seconds = _bounded_float(
        settings.get("poll_interval_seconds"),
        default=15.0,
        minimum=_MIN_POLL_INTERVAL_SECONDS,
        maximum=_MAX_POLL_INTERVAL_SECONDS,
    )
    state.update(
        {
            "schema_version": "mn.gtm_assistant.reply_monitoring.v1",
            "status": "awaiting_approved_development_delivery",
            "reason": reason,
            "started_at": state.get("started_at") or str(context.get("started_at") or "not_reported"),
            "poll_interval_seconds": interval_seconds,
            "reply_count": int(state.get("reply_count") or 0),
            "poll_count": int(state.get("poll_count") or 0),
            "match_policy": "same_development_recipient_and_reply_reference_only",
        }
    )
    _write_state(context, state)

    approval_response: dict[str, Any] | None = None
    try:
        while not stop_requested.is_set() and not stop_file.exists():
            approval_response = development_email_approval_response(context)
            if approval_response is not None:
                break
            state["poll_count"] += 1
            state["updated_at"] = str(context.get("started_at") or "not_reported")
            _write_state(context, state)
            stop_requested.wait(interval_seconds)
    finally:
        _restore_stop_handlers(previous_handlers)

    if approval_response is not None:
        approved = (
            approval_response.get("approved") is True
            and str(approval_response.get("decision") or "").strip().lower() == "approve"
        )
        if approved:
            delivery = _deliver_after_human_approval(context)
            state.update(
                {
                    "status": "development_email_sent",
                    "reason": "human_approved",
                    "updated_at": str(context.get("started_at") or "not_reported"),
                }
            )
            _write_state(context, state)
            if bool(settings.get("enabled", False)):
                return _monitor_forever(
                    context,
                    settings=settings,
                    username=str(os.environ.get(SMTP_USERNAME_ENV) or "").strip(),
                    password=str(os.environ.get(SMTP_PASSWORD_ENV) or ""),
                    development_recipient=str(os.environ.get(SMTP_DEV_RECIPIENT_ENV) or "").strip(),
                    outbound_message_id=str(delivery.get("message_id") or "").strip(),
                )
            return _result_from_state(context)

        state.update(
            {
                "status": "approval_rejected",
                "reason": "human_rejected_or_revised",
                "updated_at": str(context.get("started_at") or "not_reported"),
            }
        )
        _write_state(context, state)
        return _result_from_state(context)

    state.update(
        {
            "status": "stopped",
            "stop_reason": "signal" if stop_requested.is_set() else "stop_file",
            "updated_at": str(context.get("started_at") or "not_reported"),
        }
    )
    _write_state(context, state)
    return state


def _monitor_forever(
    context: dict[str, Any],
    *,
    settings: Mapping[str, Any],
    username: str,
    password: str,
    development_recipient: str,
    outbound_message_id: str,
    imap_factory: _ImapFactory = imaplib.IMAP4_SSL,
) -> dict[str, Any]:
    state = _load_state(context)
    stop_requested = threading.Event()
    previous_handlers = _install_stop_handlers(stop_requested)
    stop_file = _stop_file(context, settings)
    interval_seconds = _bounded_float(
        settings.get("poll_interval_seconds"),
        default=15.0,
        minimum=_MIN_POLL_INTERVAL_SECONDS,
        maximum=_MAX_POLL_INTERVAL_SECONDS,
    )
    state.update(
        {
            "schema_version": "mn.gtm_assistant.reply_monitoring.v1",
            "status": "monitoring",
            "started_at": state.get("started_at") or str(context.get("started_at") or "not_reported"),
            "poll_interval_seconds": interval_seconds,
            "reply_count": int(state.get("reply_count") or 0),
            "poll_count": int(state.get("poll_count") or 0),
            "matched_reply_fingerprints": list(state.get("matched_reply_fingerprints") or [])[-_MAX_REPLY_FINGERPRINTS:],
            "match_policy": "same_development_recipient_and_reply_reference_only",
        }
    )
    _write_state(context, state)

    try:
        while not stop_requested.is_set() and not stop_file.exists():
            try:
                replies = _poll_replies_once(
                    settings=settings,
                    username=username,
                    password=password,
                    development_recipient=development_recipient,
                    outbound_message_id=outbound_message_id,
                    imap_factory=imap_factory,
                )
                seen = set(str(value) for value in state["matched_reply_fingerprints"])
                new_fingerprints = [reply["fingerprint"] for reply in replies if reply["fingerprint"] not in seen]
                state["matched_reply_fingerprints"] = (
                    [*state["matched_reply_fingerprints"], *new_fingerprints][-_MAX_REPLY_FINGERPRINTS:]
                )
                state["reply_count"] += len(new_fingerprints)
                state["last_error"] = ""
                if new_fingerprints:
                    state["last_reply_at"] = str(context.get("started_at") or "not_reported")
            except Exception:
                state["last_error"] = "imap_poll_failed"

            state["poll_count"] += 1
            state["updated_at"] = str(context.get("started_at") or "not_reported")
            _write_state(context, state)
            stop_requested.wait(interval_seconds)
    finally:
        _restore_stop_handlers(previous_handlers)

    state.update(
        {
            "status": "stopped",
            "stop_reason": "signal" if stop_requested.is_set() else "stop_file",
            "updated_at": str(context.get("started_at") or "not_reported"),
        }
    )
    _write_state(context, state)
    return state


def _poll_replies_once(
    *,
    settings: Mapping[str, Any],
    username: str,
    password: str,
    development_recipient: str,
    outbound_message_id: str,
    imap_factory: _ImapFactory = imaplib.IMAP4_SSL,
) -> list[dict[str, str]]:
    host = str(settings.get("host") or "").strip().lower()
    port = _positive_int(settings.get("port"), default=ICLOUD_IMAP_PORT)
    security = str(settings.get("security") or "").strip().lower()
    if (host, port, security) != (ICLOUD_IMAP_HOST, ICLOUD_IMAP_PORT, "ssl"):
        raise RuntimeError("Reply monitoring must use the approved iCloud IMAP SSL endpoint")
    timeout_seconds = _bounded_float(
        settings.get("timeout_seconds"), default=10.0, minimum=1.0, maximum=60.0
    )

    client = imap_factory(host, port, timeout=timeout_seconds)
    try:
        _require_ok(client.login(username, password), "IMAP login failed")
        _require_ok(client.select("INBOX", readonly=True), "IMAP inbox selection failed")
        status, data = client.search(None, "UNSEEN")
        _require_ok((status, data), "IMAP unread-message search failed")
        message_numbers = _message_numbers(data)
        replies: list[dict[str, str]] = []
        for message_number in message_numbers:
            status, response = client.fetch(
                message_number,
                "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM DATE IN-REPLY-TO REFERENCES)])",
            )
            if str(status).upper() != "OK":
                continue
            headers = _header_bytes(response)
            if not headers:
                continue
            message = BytesParser(policy=policy.default).parsebytes(headers)
            if not _is_matching_reply(message, development_recipient, outbound_message_id):
                continue
            message_id = str(message.get("Message-ID") or message_number.decode("ascii", "ignore"))
            replies.append(
                {
                    "fingerprint": hashlib.sha256(message_id.encode("utf-8")).hexdigest(),
                }
            )
        return replies
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _is_matching_reply(message: Any, development_recipient: str, outbound_message_id: str) -> bool:
    sender = parseaddr(str(message.get("From") or ""))[1].strip().lower()
    if sender != development_recipient.strip().lower():
        return False
    references = " ".join(
        str(message.get(header) or "")
        for header in ("In-Reply-To", "References")
    ).lower()
    return outbound_message_id.strip().lower() in references


def _message_numbers(data: Any) -> list[bytes]:
    values: list[bytes] = []
    for entry in data or []:
        if isinstance(entry, bytes):
            values.extend(value for value in entry.split() if value)
    return values


def _header_bytes(response: Any) -> bytes:
    for entry in response or []:
        if isinstance(entry, tuple) and len(entry) >= 2 and isinstance(entry[1], bytes):
            return entry[1]
    return b""


def _require_ok(result: tuple[Any, Any], message: str) -> None:
    if str(result[0]).upper() != "OK":
        raise RuntimeError(message)


def _settings(context: Mapping[str, Any]) -> Mapping[str, Any]:
    config = context.get("config") if isinstance(context.get("config"), Mapping) else {}
    settings = config.get("reply_monitoring") if isinstance(config, Mapping) else {}
    return settings if isinstance(settings, Mapping) else {}


def _smtp_delivery_enabled(context: Mapping[str, Any]) -> bool:
    config = context.get("config") if isinstance(context.get("config"), Mapping) else {}
    settings = config.get("smtp_delivery") if isinstance(config, Mapping) else {}
    return bool(settings.get("enabled", False)) if isinstance(settings, Mapping) else False


def _delivery_receipt(context: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(str(context["run_dir"])) / DELIVERY_RECEIPT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_state(context: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(str(context["run_dir"])) / DEVELOPMENT_REPLY_MONITORING_STATE_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(context: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    write_json(
        Path(str(context["run_dir"])) / DEVELOPMENT_REPLY_MONITORING_STATE_PATH,
        dict(state),
    )


def _not_started(context: Mapping[str, Any], reason: str) -> dict[str, Any]:
    state = {
        "schema_version": "mn.gtm_assistant.reply_monitoring.v1",
        "status": "not_started",
        "reason": reason,
        "reply_count": 0,
        "poll_count": 0,
        "match_policy": "same_development_recipient_and_reply_reference_only",
    }
    _write_state(context, state)
    return _result_from_state(context)


def _result_from_state(context: Mapping[str, Any]) -> dict[str, Any]:
    state = _load_state(context)
    final_artifact = _read_final_artifact(context)
    return {
        "status": state.get("status", "unknown"),
        "reply_monitoring": {
            "status": state.get("status", "unknown"),
            "reason": state.get("reason", ""),
            "reply_count": int(state.get("reply_count") or 0),
            "state_artifact": DEVELOPMENT_REPLY_MONITORING_STATE_PATH,
        },
        "final_artifact": final_artifact,
        "output_files": [
            DEVELOPMENT_REPLY_MONITORING_STATE_PATH,
            *(["final_artifact.json"] if final_artifact else []),
        ],
    }


def _read_final_artifact(context: Mapping[str, Any]) -> dict[str, Any] | None:
    path = Path(str(context["run_dir"])) / "final_artifact.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _stop_file(context: Mapping[str, Any], settings: Mapping[str, Any]) -> Path:
    value = str(settings.get("stop_file") or Path(str(context["run_dir"])) / "STOP")
    value = value.replace("${MN_RUN_DIR}", str(context["run_dir"]))
    return Path(os.path.expandvars(value)).expanduser()


def _install_stop_handlers(stop_requested: threading.Event) -> dict[int, Any]:
    previous: dict[int, Any] = {}

    def request_stop(_signum: int, _frame: Any) -> None:
        stop_requested.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            previous[signum] = signal.signal(signum, request_stop)
        except ValueError:
            continue
    return previous


def _restore_stop_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        try:
            signal.signal(signum, handler)
        except ValueError:
            continue


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


__all__ = [
    "DEVELOPMENT_REPLY_MONITORING_STATE_PATH",
    "ICLOUD_IMAP_HOST",
    "ICLOUD_IMAP_PORT",
    "monitor_development_email_replies",
]
