FROM python:3.12-slim

WORKDIR /app

# gcc/g++/make required for CmdStan compilation (Prophet dependency)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install CmdStan at build time so Prophet doesn't attempt a download at runtime
RUN python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8004

# Shell form so Cloud Run's $PORT env var is expanded at runtime
CMD ["sh", "-c", "exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8004}"]
