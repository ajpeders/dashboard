FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

# Runs behind the dashboard nginx proxy on the internal web network only.
# 2 workers is plenty for occasional toggle clicks.
EXPOSE 8080
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "--timeout", "40", "app:app"]
