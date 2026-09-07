from payments.payment_service import execute_payment


def checkout(db, gateway, payment):
    return execute_payment(db, gateway, payment)
