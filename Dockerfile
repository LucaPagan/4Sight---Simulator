FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY backend ./backend
RUN pip install --no-cache-dir -c requirements.lock .
COPY alembic.ini ./
COPY migrations ./migrations
RUN mkdir -p /app/artifacts
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "audience_simulator.api:app", "--host", "0.0.0.0", "--port", "8000"]
