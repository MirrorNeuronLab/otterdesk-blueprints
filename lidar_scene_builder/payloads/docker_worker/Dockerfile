FROM nvcr.io/nvidia/nre/nurec-ga:26.10.00@sha256:cec2374b07e7f48d08cb7dafd7ec296a0b3dafabc46aa8e96b1564842021776d

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && /usr/bin/python3 -m venv /opt/mn-venv \
    && /opt/mn-venv/bin/python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'

# The SDK runs in Ubuntu's Python 3.12. NVIDIA's Bazel runtime keeps its
# bundled Python 3.13, native OpenUSD bindings and CUDA libraries together.
ENV PATH="/opt/mn-venv/bin:${PATH}" \
    NUREC_RUNFILES=/app/run.runfiles \
    NUREC_PYTHON=/app/run.runfiles/_main/_run.venv/bin/python3 \
    NUREC_ENABLE_COLORED_EXCEPTIONS=0
RUN RUNFILES_DIR="$NUREC_RUNFILES" PYTHONPATH="$NUREC_RUNFILES/_main" \
    "$NUREC_PYTHON" -s -c 'import importlib.util, numpy, torch; from pxr import Usd; assert importlib.util.find_spec("nurec.utils.io.export.gaussian_usd_writer")'

WORKDIR /app
COPY domain/ /app/domain/
ENTRYPOINT []
CMD ["/opt/mn-venv/bin/python3", "-m", "mn_sdk.step_runtime"]
