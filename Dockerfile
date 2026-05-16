
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app/

RUN if [ -f "requirements.txt" ]; then pip install --no-cache-dir -r requirements.txt; fi

CMD ["python", "run.py", "--adapter", "adapters.myteam:Engine", "--fk-policy", "cascade"]