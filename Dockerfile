FROM python:3.10-slim

WORKDIR /app

COPY . /app

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "run.py", "--adapter", "adapters.myteam:Engine", "--fk-policy", "tombstone", "--randomized-seeds", "9999", "31415", "27182", "16180", "11235", "--rand-peers", "5", "--rand-ops", "150", "--out", "/dev/stdout"]