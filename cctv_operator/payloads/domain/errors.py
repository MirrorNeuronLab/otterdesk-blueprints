"""Safe local failures, kept distinct from untrusted NVIDIA response details."""


class CameraStateError(RuntimeError):
    """A local camera-state failure whose message contains no private input."""
