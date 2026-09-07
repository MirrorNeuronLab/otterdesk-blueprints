from payments.payment_service import execute_payment, decide_fraud


def handle_payment(db, gateway, payment):
    if decide_fraud(payment):
        return "rejected"
    return execute_payment(db, gateway, payment)
