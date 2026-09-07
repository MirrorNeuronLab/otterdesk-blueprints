"""Ledger persistence belongs to the same local transaction as payment records."""


def record(db, payment):
    db.execute("INSERT INTO ledger_entries VALUES (?)", (payment.id,))
