def normalize_name(value):
    name = value.strip()
    if not name:
        raise ValueError("A name is required")
    return name
