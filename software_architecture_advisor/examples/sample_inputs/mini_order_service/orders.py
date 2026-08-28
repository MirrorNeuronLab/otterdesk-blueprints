from .notifications import send_order_confirmation


def create_order(customer_id: str, sku: str) -> dict[str, str]:
    order = {"customer_id": customer_id, "sku": sku, "status": "created"}
    send_order_confirmation(order)
    return order
