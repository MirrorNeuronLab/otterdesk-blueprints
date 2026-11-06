"""App-owned default responses still require the ordinary Core approval receipt."""
import pytest
from test_code_verifier import modules, context, authority, prepare_rules


def test_rules_declare_approve_all_as_the_default_but_still_require_a_core_decision(modules, context, authority):
    prepare_rules(modules, context)
    rules = modules['artifacts'].read(context, 'rules.json')
    request = modules['rule_review'].review_requests(rules)[1][0]
    assert request['default_answer'] == {'option_id': 'approve'}
    authority.publish(context.run_id, 'human_input_requested', request)
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['rule_review'].require_approved_rules(context, rules)
    assert authority.approve(context)['approval']['status'] == 'approved'


@pytest.mark.parametrize('expired_before_wait', [False, True])
def test_review_expiry_is_reported_specifically_with_a_recovery_action(modules, context, authority, monkeypatch, expired_before_wait):
    prepare_rules(modules, context)
    review = modules['rule_review']
    request = review.review_requests(modules['artifacts'].read(context, 'rules.json'))[1][0]
    def expire(run_id, request_id, **kwargs):
        authority.publish(run_id, 'human_input_timeout', {'request_id': request_id, 'status': 'expired'})
    if expired_before_wait:
        authority.publish(context.run_id, 'human_input_requested', request)
        expire(context.run_id, request['request_id'])
    else:
        monkeypatch.setattr(review.human_interactions, 'await_human_decision', expire)
    with pytest.raises(review.RulesReviewRequired, match='Rule review expired.*Start a new run'):
        authority.approve(context)
    assert modules['artifacts'].read(context, 'rules-review.json')['status'] == 'expired'
    with pytest.raises(review.RulesReviewRequired):
        review.require_approved_rules(context, modules['artifacts'].read(context, 'rules.json'))
