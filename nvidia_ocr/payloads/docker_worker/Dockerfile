FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-impress libreoffice-calc fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir "Pillow>=12,<13" "pypdfium2>=4.30,<6"
WORKDIR /app
COPY domain/ /app/domain/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
