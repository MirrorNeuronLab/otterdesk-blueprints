from . import payment_service


def retry_refund(db, gateway, payment):
    return payment_service.retry_payment(db, gateway, payment)
