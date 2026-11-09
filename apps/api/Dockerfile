FROM python:3.13.18-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY packages/framework ./packages/framework
COPY apps/api ./apps/api
COPY LICENSE NOTICE requirements.lock ./
RUN python -m pip install --no-cache-dir -c requirements.lock ./packages/framework ./apps/api \
    && useradd --create-home --uid 10001 praxioj
COPY examples/problems ./examples/problems
COPY scripts/start-api.sh ./scripts/start-api.sh
USER praxioj
EXPOSE 8000
CMD ["sh", "scripts/start-api.sh"]
