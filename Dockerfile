FROM python:3.11-slim

# Install system dependencies including DNS utilities
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    git \
    curl \
    ca-certificates \
    dnsutils \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Create non-root user for Hugging Face
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set working directory
WORKDIR $HOME/app

# Copy requirements and install Python dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY --chown=user . .

# Expose port (Render uses 10000, HF uses 7860)
EXPOSE 10000

# Run Streamlit - port configurable via PORT env var (defaults to 10000 for Render)
CMD streamlit run app.py --server.port=${PORT:-10000} --server.address=0.0.0.0 --server.fileWatcherType=none
