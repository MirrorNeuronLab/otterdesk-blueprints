# Synthetic payment system

This fixture is invented for software tests; it is not production evidence.
The payment module intentionally orchestrates checkout in a single process.
Payment and ledger writes currently share one local database transaction.
Gateway charges and notifications are external effects and do not share that transaction.
The declared checkout workflow includes payments.payment_service and payments.checkout.
Demo incident DEMO-001 involved payments.payment_service; this is synthetic supplied data.
