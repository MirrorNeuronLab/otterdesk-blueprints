"""Blueprint model choices and narrowly scoped Local Spark provider settings."""

import re
from urllib.parse import urlsplit

SPARK_MODEL = "spark/muse-glimmer-30b"
SPARK_BASE_URL = "http://10.0.4.32:8000/v1"
MODEL_LABELS = {
    "Muse Spark 1.3 FreeOpenCode Zen": "opencode/muse-spark-1.3-contributor-free",
    "Muse Glimmer 30BLocal Spark": SPARK_MODEL,
}


def normalize_model(value):
    if not isinstance(value, str):
        raise ValueError("opencode.model must be provider/model")
    model = MODEL_LABELS.get(value, value)
    if len(model) > 256 or not re.fullmatch(
        r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./:-]+", model
    ):
        raise ValueError("opencode.model must be provider/model")
    return model


def validate_spark_url(value):
    if not isinstance(value, str):
        raise ValueError(
            "opencode.spark_base_url must be an HTTP(S) endpoint ending in /v1"
        )
    url = urlsplit(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path != "/v1"
    ):
        raise ValueError(
            "opencode.spark_base_url must be an HTTP(S) endpoint ending in /v1"
        )
    return value


def provider_config(settings):
    if settings["model"] != SPARK_MODEL:
        return {}
    return {
        "provider": {
            "spark": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local Spark",
                "options": {"baseURL": settings["spark_base_url"], "apiKey": "dummy"},
                "models": {"muse-glimmer-30b": {"name": "Muse Glimmer 30B"}},
            }
        }
    }
