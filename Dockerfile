FROM python:3.11-slim

# System dependencies: Manim (cairo, pango), ffmpeg, fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    fonts-inter \
    fonts-jetbrains-mono \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cached unless pyproject.toml changes)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "manim>=0.18.0" \
    "pydantic>=2.0" \
    "flask>=2.3" \
    "playwright>=1.40" \
    "edge-tts>=6.1" \
    "gTTS>=2.3" \
    "openai>=1.0" \
    "anthropic>=0.30" \
    "google-genai>=1.0" \
    && playwright install --with-deps chromium

# Copy source and install package
COPY . .
RUN pip install --no-cache-dir -e .

# Output volume
RUN mkdir -p /app/manimator_output
VOLUME /app/manimator_output

# Run web UI by default, bind to all interfaces so host can reach it
ENV MANIMATOR_HOST=0.0.0.0
ENV MANIMATOR_PORT=5100
EXPOSE 5100

ENTRYPOINT ["python", "-m"]
CMD ["manimator.web"]
