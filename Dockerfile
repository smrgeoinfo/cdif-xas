FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Java
RUN apt-get update && \
    apt-get install -y default-jdk && \
    rm -rf /var/lib/apt/lists/*

# Verify installs
RUN java -version && python --version

WORKDIR /app

# Copy dependency files and install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

COPY ./api/* /app/
COPY ./resources /app/resources

CMD ["uv", "run", "uvicorn", "api.api:app", "--host", "0.0.0.0", "--port", "80"]
