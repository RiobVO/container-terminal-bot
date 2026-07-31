FROM python:3.12-slim

# Таймзона процесса: datetime.now() будет возвращать Ташкентское локальное
# время — иначе в контейнере было бы UTC, и даты прибытия/регистрации
# расходились бы на 5 часов с тем, что видит пользователь.
ENV TZ=Asia/Tashkent

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

USER appuser

CMD ["python", "bot.py"]
