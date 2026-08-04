FROM python:3.13-slim

WORKDIR /app

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ .
# Alongside the server, because build_info.py looks for it next to the
# application: it is both the changelog the panel shows and the last
# fallback for the build id, and a container carries no .git to ask.
COPY CHANGELOG.md .

EXPOSE 5000

# Single worker is a design decision, not a default: game state lives in this
# process's memory. See server/wsgi.py before changing -w.
CMD ["gunicorn", "-w", "1", "--threads", "100", "-b", "0.0.0.0:5000", "wsgi:app"]
