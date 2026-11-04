FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# mirrorneuron: skill-dependencies
# The SDK injects declared capability dependencies at preparation.
# mirrorneuron: skill-dependencies-end
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt
WORKDIR /mn/job
ENTRYPOINT []
