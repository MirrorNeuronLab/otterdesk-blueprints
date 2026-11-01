FROM python:3.12-slim-bookworm
WORKDIR /app
COPY docker_worker/requirements.txt /tmp/web-lab-requirements.txt
RUN pip install --no-cache-dir -r /tmp/web-lab-requirements.txt
COPY docker_worker/prepare_visualizer.py docker_worker/visualizer-assets.json /tmp/web-lab-build/
RUN python /tmp/web-lab-build/prepare_visualizer.py
COPY domain/ /app/domain/
COPY prompts/ /app/prompts/
COPY web_assets/ /app/web_assets/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
