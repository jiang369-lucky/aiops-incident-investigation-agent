FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY skills ./skills
COPY knowledge ./knowledge
RUN pip install --no-cache-dir -e ".[api,mcp]"

EXPOSE 8000
CMD ["uvicorn", "incident_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
