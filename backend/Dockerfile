FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sutra ./sutra
COPY bench ./bench
COPY tests ./tests

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "sutra.main:app", "--host", "0.0.0.0", "--port", "8000"]
