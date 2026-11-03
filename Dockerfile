FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY marketsignal ./marketsignal
RUN python -m pip install --no-cache-dir '.[postgres]'

# No root permissions or cloud credential files required at runtime.
USER 65532:65532
ENTRYPOINT ["python", "-m", "marketsignal"]
CMD ["collect", "--max-markets", "150", "--max-pages", "8"]
