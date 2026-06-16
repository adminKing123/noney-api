FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN pwd
RUN ls -la
RUN find .

ENV PYTHONPATH=/app
ENV PORT=8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--chdir", "/app", "app:app"]