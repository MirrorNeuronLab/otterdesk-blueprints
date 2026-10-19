"""SYNTHETIC EXAMPLE ONLY: tiny source fixture for a read-only review."""
def create_task(name, password, store):
    if not name.strip():
        raise ValueError("Task name is required")
    store.write({"name": name, "password": password})
