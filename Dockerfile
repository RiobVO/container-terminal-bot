FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -m -u 1000 appuser && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

COPY . .

CMD ["python", "bot.py"]
