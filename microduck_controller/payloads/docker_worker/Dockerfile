FROM node:22-alpine AS web-build
WORKDIR /build
COPY web_app/package.json web_app/package-lock.json ./
RUN npm ci
COPY web_app/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY agents/ /app/agents/
COPY domain/ /app/domain/
COPY knowledge/ /app/knowledge/
COPY services/ /app/services/
COPY --from=web-build /build/dist/ /app/web_dist/
ENV MICRODUCK_STATIC_DIR=/app/web_dist
EXPOSE 8080
CMD ["python3.11", "services/duck_control_service.py"]
