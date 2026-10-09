FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements-lock.txt /app/backend/requirements-lock.txt
RUN pip install --no-cache-dir -r /app/backend/requirements-lock.txt
COPY backend/ /app/backend/
COPY fixtures/ /app/fixtures/
COPY --from=frontend /ui/dist /app/frontend/dist
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
