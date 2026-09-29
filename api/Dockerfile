FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data
ENV AI_OUTPUT_DIR=/app/ai_output
ENV CUSTOMER_EMAILS_FILE=/app/config/customer_emails.csv

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
