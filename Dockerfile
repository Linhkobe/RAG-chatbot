FROM python:3.12-slim 

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:8501/ || exit 1

ENTRYPOINT ["streamlit", "run", "test_agent.py", "--server.port=8501", "--server.address=0.0.0.0"]