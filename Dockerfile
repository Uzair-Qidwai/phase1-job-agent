FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HOME=/home/app \
    LITELLM_LOCAL_MODEL_COST_MAP=True
WORKDIR /app
COPY deploy/requirements.lock /app/deploy/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r deploy/requirements.lock \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app
COPY src /app/src
COPY migrations /app/migrations
COPY data/candidate_profile.json /app/data/candidate_profile.json
COPY deploy/entrypoint.py deploy/healthcheck.py /app/deploy/
USER 10001:10001
ENTRYPOINT ["python", "/app/deploy/entrypoint.py"]
CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
