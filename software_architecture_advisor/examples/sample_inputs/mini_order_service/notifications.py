from .orders import create_order


def send_order_confirmation(order: dict[str, str]) -> None:
    if order.get("status") == "retry":
        create_order(order["customer_id"], order["sku"])
