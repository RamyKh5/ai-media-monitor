# Use official lightweight Python image
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/app/.cache

# --- STEP 1: Install system dependencies ---
# Why first? These are large and change rarely. Installing them first
# allows Docker to cache this layer. If you change your code later,
# Docker won't reinstall system deps—it reuses the cached layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# --- STEP 2: Set working directory ---
# Why now? All subsequent COPY and RUN commands will use /app as base path.
WORKDIR /app

# --- STEP 3: Copy ONLY requirements.txt first ---
# Why before copying all code? Docker caches layers. If requirements.txt
# hasn't changed, Docker reuses the cached pip install layer, saving time.
COPY requirements.txt .

# --- STEP 4: Install Python dependencies ---
# Why now? This layer is cached. If requirements.txt doesn't change,
# Docker skips this step entirely on rebuilds.
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

#TEP 5: Install Playwright browser binaries ---
# Why after pip install? Playwright needs to be installed first (from
# requirements.txt) before you can run the install command.
RUN playwright install chromium --with-deps

#STEP 6: Copy the rest of your code 
# Why last? Code changes frequently. By putting this at the end,
# Docker can reuse ALL previous cached layers when you change code.
# Only this layer gets rebuilt on code changes.
COPY . .

# --- STEP 7: Define the default command ---
CMD ["python", "main.py"]