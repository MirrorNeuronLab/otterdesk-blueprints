"""Payment execution, retries, fraud checks, notifications and reconciliation.

The local database transaction currently protects payment and ledger writes.
Extracting a remote service would require a different consistency protocol.
"""
from payments import ledger
from .notifications import notify


def execute_payment(db, gateway, payment):
    """Charge the gateway and record the payment; gateway idempotency is unresolved."""
    with db.transaction():
        gateway.charge(payment)
        db.execute("INSERT INTO payments VALUES (?)", (payment.id,))
        ledger.record(db, payment)
    notify(payment)


def retry_payment(db, gateway, payment):
    """Retry orchestration currently repeats all side effects."""
    return execute_payment(db, gateway, payment)


def decide_fraud(payment):
    return payment.amount > 10000


def reconcile_ledger(db):
    return db.execute("SELECT * FROM ledger_entries")
