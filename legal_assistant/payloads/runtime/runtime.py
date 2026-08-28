"""Legal Assistant runtime preparation boundary.

The runtime resolves manifest-projected configuration and the platform-staged
document folder. It deliberately does not import legal-review workers or
perform legal document processing.
"""

from domain.runtime_services import append_event, build_ocr_runtime, runtime_context_for_step

__all__ = ["append_event", "build_ocr_runtime", "runtime_context_for_step"]
