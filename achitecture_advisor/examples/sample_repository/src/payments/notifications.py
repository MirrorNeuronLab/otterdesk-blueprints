"""Notification delivery is a distinct side effect."""


def notify(payment):
    payment.notification_sink.send(payment.id)
