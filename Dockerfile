FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-lock.tx[t] ./
RUN if [ -f requirements-lock.txt ]; then \
        echo ">> instalando desde requirements-lock.txt (versiones fijas)"; \
        pip install --no-cache-dir -r requirements-lock.txt; \
    else \
        echo ">> AVISO: no hay requirements-lock.txt, se instala sin fijar versiones"; \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

RUN useradd --create-home --uid 10001 agente \
 && chown -R agente:agente /app
USER agente

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "frontend/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
