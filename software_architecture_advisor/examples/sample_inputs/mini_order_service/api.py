from .orders import create_order


def submit_order(customer_id: str, sku: str) -> dict[str, str]:
    return create_order(customer_id, sku)
