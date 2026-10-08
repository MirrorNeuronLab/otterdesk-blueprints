"""Fixed investigation budgets; the output folder is the only operator setting."""


def investigation_policy():
    return {"max_records": 20000, "max_scan_bytes": 8388608,
            "max_candidates": 256,
            "max_hops": 4, "max_nodes": 128, "max_edges": 128,
            "max_history_records": 100000, "max_history_bytes": 134217728,
            "max_witness_records": 256, "max_log_bytes": 4194304,
            "max_log_records": 2000, "log_timeout_seconds": 20}
