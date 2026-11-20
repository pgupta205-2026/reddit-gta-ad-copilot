FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PORT=8080

WORKDIR /srv/app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md DESIGN_SPEC.md ./
COPY app ./app

RUN uv sync --no-dev --no-editable

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.fast_api_app:app", "--host", "0.0.0.0", "--port", "8080"]
