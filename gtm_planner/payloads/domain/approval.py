"""Marketing approval requests use the shared Core-authoritative helper."""

from mn_sdk.human_interactions import poll_approval


def approval(context, key, preview, *, expires_at):
    return poll_approval(context["run_id"], key, preview, expires_at=expires_at)
