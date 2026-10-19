"""Architecture review model choices; SDK owns placement and gateway routes."""
import os
import re
from mn_opencode_skill import OpenCodeGateway
from mn_sdk.model_access import ensure_runtime_model, remote_model_api_base
from mn_sdk.model_runtime import load_model_catalog, resolve_model_entry

DEFAULT_MODEL = "mn/default"
MODEL_LABELS = {
    "Runtime default": DEFAULT_MODEL,
    "Muse Spark 1.3 FreeOpenCode Zen": "opencode/muse-spark-1.3-contributor-free",
    "Muse Glimmer 30BLocal Spark": "spark/muse-glimmer-30b",
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


def prepare_gateway(settings):
    selection = normalize_model(settings["model"])
    catalog_id = selection.removeprefix("mn/") if selection.startswith("mn/") else selection
    # Do not reinterpret an unavailable OpenCode provider as a model to download.
    try:
        resolve_model_entry(catalog_id, catalog=load_model_catalog())
    except (KeyError, ValueError) as exc:
        raise ValueError("The selected review model must be registered in the runtime model catalog.") from exc
    provider = (os.environ.get("MN_LLM_PROVIDER") or "docker_model_runner") if catalog_id == "default" else "docker_model_runner"
    binding = ensure_runtime_model("llm", catalog_id, provider=provider)
    host_api_base, node = binding.host_api_base, binding.node
    if catalog_id == "default" and provider in {"litellm", "litellm_proxy"}:
        # The SDK projects the registered default onto the node's gateway.
        # Docker uses its internal URL; OpenShell needs the advertised host.
        node = os.environ.get("MN_SELECTED_RUNTIME_NODE") or node
        _, separator, host = node.rpartition("@")
        if not separator or not host:
            raise ValueError("Remote review requires the selected runtime node's advertised gateway host")
        host_api_base = remote_model_api_base({}, {"api_base": binding.api_base}, host)
    descriptor = {"api_base": host_api_base, "model": binding.api_model,
                  "catalog_id": binding.catalog_id, "node": node}
    gateway_binding(descriptor).provider(selection)
    return descriptor


def gateway_binding(descriptor):
    if not isinstance(descriptor, dict) or set(descriptor) != {"api_base", "model", "catalog_id", "node"}:
        raise ValueError("Review requires a prepared runtime gateway descriptor")
    return OpenCodeGateway(api_base=descriptor["api_base"], model=descriptor["model"],
                           api_key=os.environ.get("MN_LLM_API_KEY") or "not-needed")
