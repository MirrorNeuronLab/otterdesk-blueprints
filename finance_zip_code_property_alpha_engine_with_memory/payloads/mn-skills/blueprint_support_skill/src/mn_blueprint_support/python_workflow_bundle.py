from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, Union

from .support import apply_quick_test, log_status, progress
from .utils import deep_merge, read_json_file


PathLike = Union[str, Path]
PythonWorkflowCompiler = Callable[..., PathLike]
COMPILER_METADATA_KEYS = {
    "compiler_version",
    "generated_at",
    "generated_by",
    "manifest_schema",
    "python_source_mode",
    "source_hash",
}
SOURCE_MANIFEST_FIELDS_TO_PRESERVE = ("description",)
SOURCE_SIDECAR_FILES = (
    Path("config/default.json"),
    Path("scenario.json"),
    Path("requirements.txt"),
)


@dataclass(frozen=True)
class PythonWorkflowBundleSpec:
    """Blueprint-facing configuration for compiling Python SDK workflows."""

    blueprint_id: str
    workflow_class: type[Any]
    description: str
    default_output_dir: Path | None = None
    includes: Sequence[str | Path] = ()
    excludes: Sequence[str] = ()
    metadata: Mapping[str, Any] | None = None
    source_manifest_path: Path | None = None
    initial_inputs: dict[str, list[dict[str, Any]]] | None = None
    include_source_dir: bool = True
    daemon: bool | None = None
    complete_on_final: bool | None = None
    status_message: str | None = None


def python_workflow_spec_from_blueprint_dir(
    blueprint_dir: str | Path,
    *,
    default_output_dir: str | Path | None = None,
) -> PythonWorkflowBundleSpec:
    """Build a bundle spec from blueprint-owned manifest metadata."""

    blueprint_path = Path(blueprint_dir).resolve()
    manifest_path = blueprint_path / "manifest.json"
    manifest = read_json_file(manifest_path)
    metadata = manifest.get("metadata") or {}
    workflow_config = metadata.get("python_workflow") or {}
    if not isinstance(workflow_config, dict):
        raise ValueError("manifest metadata.python_workflow must be a JSON object")

    module_name = str(workflow_config.get("module") or "workflow")
    class_name = str(workflow_config.get("class") or "")
    if not class_name:
        raise ValueError("manifest metadata.python_workflow.class is required")

    workflow_module = _load_workflow_module(blueprint_path, module_name, metadata)
    workflow_class = getattr(workflow_module, class_name)
    blueprint_id = str(metadata.get("blueprint_id") or blueprint_path.name)
    description = str(
        workflow_config.get("description")
        or manifest.get("description")
        or f"Generate the {blueprint_id} Python workflow bundle."
    )

    return PythonWorkflowBundleSpec(
        blueprint_id=blueprint_id,
        workflow_class=workflow_class,
        description=description,
        default_output_dir=Path(default_output_dir) if default_output_dir else blueprint_path,
        includes=tuple(workflow_config.get("includes") or ()),
        excludes=tuple(workflow_config.get("excludes") or ()),
        metadata=workflow_config.get("metadata") if isinstance(workflow_config.get("metadata"), dict) else None,
        source_manifest_path=manifest_path,
        initial_inputs=workflow_config.get("initial_inputs") if isinstance(workflow_config.get("initial_inputs"), dict) else None,
        include_source_dir=bool(workflow_config.get("include_source_dir", True)),
        daemon=workflow_config.get("daemon") if isinstance(workflow_config.get("daemon"), bool) else None,
        complete_on_final=workflow_config.get("complete_on_final") if isinstance(workflow_config.get("complete_on_final"), bool) else None,
        status_message=workflow_config.get("status_message"),
    )


def generate_python_workflow_bundle_from_blueprint_dir(
    blueprint_dir: str | Path,
    output_dir: str | Path | None = None,
    *,
    quick_test: bool = False,
    compiler: PythonWorkflowCompiler | None = None,
) -> Path:
    spec = python_workflow_spec_from_blueprint_dir(
        blueprint_dir,
        default_output_dir=output_dir,
    )
    return generate_python_workflow_bundle(
        spec,
        output_dir,
        quick_test=quick_test,
        compiler=compiler,
    )


def generate_python_workflow_bundle(
    spec: PythonWorkflowBundleSpec,
    output_dir: str | Path | None = None,
    *,
    quick_test: bool = False,
    compiler: PythonWorkflowCompiler | None = None,
) -> Path:
    """Compile a Python SDK workflow into a MirrorNeuron bundle.

    This is intentionally a thin blueprint-support facade over the Python SDK
    compiler. The Python SDK owns the workflow decorators and graph compiler;
    the blueprint support skill owns the reusable blueprint generation UX:
    status logging, quick-test metadata, default output handling, and a stable
    command-line wrapper for blueprint folders.
    """

    bundle_dir = Path(output_dir or spec.default_output_dir or Path.cwd())
    source_manifest = _load_source_manifest(spec.source_manifest_path)
    metadata = _generation_metadata(
        _blueprint_owned_metadata(source_manifest),
        spec.metadata,
        quick_test=quick_test,
    )
    log_status(
        spec.blueprint_id,
        spec.status_message or "generating Python SDK workflow bundle",
        phase="generate",
        details={
            "output_dir": str(bundle_dir),
            "quick_test": quick_test,
            "includes": [str(item) for item in spec.includes],
        },
    )

    workflow_compiler = compiler or _mn_sdk_to_bundle
    compiler_kwargs: dict[str, Any] = {
        "blueprint_id": spec.blueprint_id,
        "include_source_dir": spec.include_source_dir,
        "includes": list(spec.includes),
        "excludes": list(spec.excludes),
        "metadata": metadata,
        "initial_inputs": spec.initial_inputs,
    }
    if spec.daemon is not None:
        compiler_kwargs["daemon"] = spec.daemon
    if spec.complete_on_final is not None:
        compiler_kwargs["complete_on_final"] = spec.complete_on_final

    generated_bundle_dir = Path(
        workflow_compiler(spec.workflow_class, bundle_dir, **compiler_kwargs)
    )
    _apply_source_manifest_fields(generated_bundle_dir / "manifest.json", source_manifest)
    _copy_source_sidecars(generated_bundle_dir, spec.source_manifest_path)
    log_status(
        spec.blueprint_id,
        "Python SDK workflow bundle generated",
        phase="generate",
        details={"bundle_dir": str(generated_bundle_dir), "quick_test": quick_test},
    )
    return generated_bundle_dir


def build_python_workflow_bundle_parser(
    spec: PythonWorkflowBundleSpec,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=spec.description)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=spec.default_output_dir or Path.cwd(),
        help="Directory where manifest.json and payloads/ will be written.",
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Record quick-test metadata and honor MN_BLUEPRINT_QUICK_TEST.",
    )
    return parser


def run_python_workflow_bundle_cli(
    spec: PythonWorkflowBundleSpec,
    argv: list[str] | None = None,
    *,
    output_fn: Callable[[str], None] | None = None,
    stderr_fn: Callable[[str], None] | None = None,
    compiler: PythonWorkflowCompiler | None = None,
) -> Path:
    parser = build_python_workflow_bundle_parser(spec)
    args = parser.parse_args(argv)
    quick_test = apply_quick_test(args, {})
    bundle_dir = generate_python_workflow_bundle(
        spec,
        args.output_dir,
        quick_test=quick_test,
        compiler=compiler,
    )
    _emit_stderr(progress("bundle generated", 1, 1), stderr_fn)
    (output_fn or print)(str(bundle_dir))
    return bundle_dir


def build_source_python_workflow_bundle_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Python source-mode blueprint bundle.")
    parser.add_argument(
        "--blueprint-dir",
        type=Path,
        default=Path.cwd(),
        help="Blueprint directory containing manifest.json and workflow source.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where manifest.json and payloads/ will be written.",
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Record quick-test metadata and honor MN_BLUEPRINT_QUICK_TEST.",
    )
    return parser


def run_source_python_workflow_bundle_cli(
    argv: list[str] | None = None,
    *,
    output_fn: Callable[[str], None] | None = None,
    stderr_fn: Callable[[str], None] | None = None,
    compiler: PythonWorkflowCompiler | None = None,
) -> Path:
    parser = build_source_python_workflow_bundle_parser()
    args = parser.parse_args(argv)
    quick_test = apply_quick_test(args, {})
    bundle_dir = generate_python_workflow_bundle_from_blueprint_dir(
        args.blueprint_dir,
        args.output_dir,
        quick_test=quick_test,
        compiler=compiler,
    )
    _emit_stderr(progress("bundle generated", 1, 1), stderr_fn)
    (output_fn or print)(str(bundle_dir))
    return bundle_dir


def _generation_metadata(
    source_metadata: Mapping[str, Any] | None,
    explicit_metadata: Mapping[str, Any] | None,
    *,
    quick_test: bool,
) -> dict[str, Any]:
    merged = deep_merge(dict(source_metadata or {}), dict(explicit_metadata or {}))
    quick = dict(merged.get("quick_test") or {})
    quick["enabled"] = bool(quick_test)
    merged["quick_test"] = quick
    merged.setdefault(
        "bundle_generator",
        {
            "module": "mn_blueprint_support.python_workflow_bundle",
            "compiler": "mn-python-sdk",
        },
    )
    return merged


def _load_source_manifest(path: Path | None) -> dict[str, Any]:
    """Best-effort read of blueprint-owned metadata for generated bundles."""

    if path is None or not path.exists():
        return {}
    try:
        return read_json_file(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _blueprint_owned_metadata(source_manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw_metadata = source_manifest.get("metadata")
    if not isinstance(raw_metadata, dict):
        return {}
    return {
        key: value
        for key, value in raw_metadata.items()
        if key not in COMPILER_METADATA_KEYS
    }


def _apply_source_manifest_fields(manifest_path: Path, source_manifest: Mapping[str, Any]) -> None:
    if not source_manifest or not manifest_path.exists():
        return
    generated_manifest = read_json_file(manifest_path)
    manifest_changed = False
    for field_name in SOURCE_MANIFEST_FIELDS_TO_PRESERVE:
        if field_name in source_manifest and field_name not in generated_manifest:
            generated_manifest[field_name] = source_manifest[field_name]
            manifest_changed = True
    if manifest_changed:
        manifest_path.write_text(
            json.dumps(generated_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _copy_source_sidecars(bundle_dir: Path, source_manifest_path: Path | None) -> None:
    if source_manifest_path is None:
        return
    source_root = source_manifest_path.parent
    for relative_path in SOURCE_SIDECAR_FILES:
        source_path = source_root / relative_path
        destination_path = bundle_dir / relative_path
        if not source_path.exists() or source_path.resolve() == destination_path.resolve():
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


def _load_workflow_module(blueprint_dir: Path, module_name: str, metadata: Mapping[str, Any]) -> Any:
    _maybe_add_local_python_sdk(blueprint_dir)
    module_path = blueprint_dir / f"{module_name.replace('.', '/')}.py"
    if not module_path.exists():
        raise ValueError(f"Python workflow module was not found: {module_path}")

    blueprint_id = str(metadata.get("blueprint_id") or blueprint_dir.name)
    digest = hashlib.sha1(str(module_path).encode("utf-8")).hexdigest()[:12]
    import_name = f"_mn_blueprint_{blueprint_id}_{digest}"
    spec = importlib.util.spec_from_file_location(import_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load Python workflow module: {module_path}")

    if str(blueprint_dir) not in sys.path:
        sys.path.insert(0, str(blueprint_dir))
    module = importlib.util.module_from_spec(spec)
    sys.modules[import_name] = module
    spec.loader.exec_module(module)
    return module


def _maybe_add_local_python_sdk(blueprint_dir: Path) -> None:
    for parent in (blueprint_dir, *blueprint_dir.parents):
        sdk_root = parent / "mn-python-sdk"
        if (sdk_root / "mn_sdk" / "__init__.py").exists() and str(sdk_root) not in sys.path:
            sys.path.insert(0, str(sdk_root))
            return


def _mn_sdk_to_bundle(
    workflow_class: type[Any],
    output_dir: PathLike,
    **compiler_kwargs: Any,
) -> Path:
    try:
        from mn_sdk import workflow
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Python workflow bundle generation requires mn-python-sdk. "
            "Install the Python SDK or add the local mn-python-sdk folder to PYTHONPATH."
        ) from exc
    return Path(workflow.to_bundle(workflow_class, output_dir, **compiler_kwargs))


def _emit_stderr(message: str, stderr_fn: Callable[[str], None] | None) -> None:
    if stderr_fn:
        stderr_fn(message)
    else:
        print(message, file=sys.stderr)
