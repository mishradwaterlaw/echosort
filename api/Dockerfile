# Base image: official Python 3.10, "slim" variant.
# "slim" = Debian-based but stripped of most non-essential packages, keeping image size down.
# We're matching api/'s requirement (Python 3.10) rather than grabbing "latest".
FROM python:3.10.5-slim

# All instructions from here on operate relative to /app inside the container.
# This also creates /app if it doesn't exist.
WORKDIR /app

# Copy ONLY requirements.txt first — not the whole api/ folder yet.
# This is the layer-caching trick: as long as requirements.txt doesn't change,
# Docker reuses the cached "pip install" layer below, even if main.py changes.
COPY requirements.txt .

# --no-cache-dir: don't let pip cache wheel files inside the image —
# saves meaningful space since we're never going to pip install again in this container.
RUN pip install --no-cache-dir -r requirements.txt

# NOW copy the rest of the api/ source code.
# This layer WILL invalidate on every code change, but that's fine —
# it's just a file copy, it's fast, and it doesn't redo the pip install above.
COPY . .

# Documents that this container's process listens on 8000.
# Doesn't actually open the port to the outside world — that's done at `docker run` time.
EXPOSE 8000

# The actual process that runs when the container starts.
# --host 0.0.0.0 is critical: binding to 127.0.0.1 would make the server only
# reachable from INSIDE the container's own network namespace, i.e. unreachable from outside.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]