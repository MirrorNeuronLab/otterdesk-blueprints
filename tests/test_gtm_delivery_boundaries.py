"""Current AgentMail delivery contracts, using synthetic provider boundaries."""

import pytest

from test_gtm_services import Provider, Stop, fixture_campaign, load


@pytest.mark.parametrize(("field", "value"), [
    ("to", ["unreviewed@example.invalid"]),
    ("cc", ["unreviewed@example.invalid"]),
    ("bcc", ["unreviewed@example.invalid"]),
    ("send_at", "2030-01-01T00:00:00Z"),
    ("subject", "Changed subject"),
    ("text", "Changed body"),
    ("html", "<p>Changed body</p>"),
    ("in_reply_to", "unreviewed-message"),
])
def test_changed_delivery_envelope_requires_new_review(tmp_path, field, value):
    delivery = load("executor", "delivery")
    state = load("executor", "state").State(tmp_path)

    class ChangedProvider(Provider):
        def get_draft(self, key):
            return {**super().get_draft(key), field: value}

    provider = ChangedProvider()
    result = delivery.deliver(state, fixture_campaign(), provider, Stop(), approval_status="approved")
    assert result == {"sent": 0, "suppressed": 0, "needs_review": 2}
    assert provider.sent == []
    assert len(state.items("delivery_review")) == 2


@pytest.mark.parametrize("boundary", ["stop", "opt_out"])
def test_control_received_after_draft_fetch_blocks_the_send_claim(tmp_path, boundary):
    delivery = load("executor", "delivery")
    state_module = load("executor", "state")
    state = state_module.State(tmp_path)
    campaign = fixture_campaign()
    campaign["recipients"] = campaign["recipients"][:1]

    class ControlledStop(Stop):
        stopped = False

        def is_set(self):
            return self.stopped

    stop = ControlledStop()

    class BoundaryProvider(Provider):
        def get_draft(self, key):
            draft = super().get_draft(key)
            if boundary == "stop":
                stop.stopped = True
            else:
                state.suppress(campaign["recipients"][0], "opt_out")
            return draft

    provider = BoundaryProvider()
    result = delivery.deliver(state, campaign, provider, stop, approval_status="approved")
    assert result["sent"] == 0
    assert provider.sent == []
    key = state_module.digest({"campaign": campaign["id"], "recipient": campaign["recipients"][0]})
    assert state.attempt(key) is None


def test_missing_provider_receipt_is_uncertain_and_never_automatically_resent(tmp_path):
    delivery = load("executor", "delivery")
    state = load("executor", "state").State(tmp_path)

    class MissingReceiptProvider(Provider):
        def send_draft(self, key):
            self.sent.append(key)
            return {}

    provider = MissingReceiptProvider()
    campaign = fixture_campaign()
    first = delivery.deliver(state, campaign, provider, Stop(), approval_status="approved")
    assert first == {"sent": 0, "suppressed": 0, "needs_review": 1}
    second = delivery.deliver(state, campaign, provider, Stop(), approval_status="approved")
    assert second == first
    assert len(provider.sent) == 1


def test_campaign_recipient_limit_is_enforced_before_review(tmp_path):
    cycle = load("executor", "cycle")
    state = load("executor", "state").State(tmp_path)
    state.put("meta", "contacts", {
        f"synthetic-{index}@example.invalid": {"Category": "client"}
        for index in range(30)
    })
    context = {"payload": {"inbox_id": "sender@example.invalid", "website_url": "https://example.invalid"},
               "config": {"marketing": {"max_campaign_recipients": 999}}}
    cycle.prepare_campaign(
        state, context, {"audience": "customer", "kind": "outreach"},
        source_id="synthetic-limit", model=lambda *_: {"subject": "Review", "paragraphs": ["Synthetic draft."]},
    )
    campaigns = state.items("campaign")
    assert len(campaigns) == 1
    assert len(campaigns[0][1]["recipients"]) == 25
