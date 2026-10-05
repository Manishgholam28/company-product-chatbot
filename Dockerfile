# syntax=docker/dockerfile:1
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.4 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/model_cache \
    PORT=8000
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY deployment/requirements.txt deployment/requirements.txt
RUN uv pip install --python /app/.venv/bin/python -r deployment/requirements.txt

COPY src/__init__.py src/retriever.py src/reranker.py src/generator.py src/rag_pipeline.py src/web_server.py src/deploy_app.py ./src/
COPY web/ ./web/
COPY data/*.txt ./data/
COPY chroma_store/ ./chroma_store/
COPY deployment/ ./deployment/
RUN /app/.venv/bin/python -m deployment.warm_models

# The reranker is cached above; runtime needs network only for existing LLM APIs.
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN useradd --create-home --uid 10001 chatbot && chown -R chatbot:chatbot /app/chroma_store /app/model_cache
USER chatbot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD /app/.venv/bin/python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=4)"
CMD ["/app/.venv/bin/gunicorn", "--config", "deployment/gunicorn.conf.py", "src.deploy_app:build_application()"]
