"""Select the reviewed reports exposed through the runtime's download contract."""

from pathlib import Path

from mn_sdk.integrations.block_publication_files import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

from .conversation_sources import REPORTS


def publish_review_files(context):
    names = (*REPORTS, "review_index.json")
    return publish_artifact_bundle(
        context,
        [
            ArtifactWrite(
                Path(name).stem,
                name,
                context.store.path(name).read_bytes(),
                kind="markdown" if name.endswith(".md") else "json",
                authoritative=True,
                mode=0o644,
            )
            for name in names
        ],
        receipt_path=context.root + "/review-publication.json",
        output_directory=context.store.run_dir,
    )
