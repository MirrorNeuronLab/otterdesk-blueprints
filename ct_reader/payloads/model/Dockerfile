FROM python:3.12-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cu130
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY inference.py server.py /app/
COPY LICENSE.md /app/LICENSE.md
ENV HF_HOME=/cache HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
