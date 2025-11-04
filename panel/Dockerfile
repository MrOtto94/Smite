# Stage 1: System dependencies and binaries
FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    unzip \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Install rathole and gost (cached layer)
FROM base AS binaries
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then ARCH="amd64"; \
    elif [ "$ARCH" = "aarch64" ]; then ARCH="arm64"; \
    else ARCH="amd64"; fi && \
    echo "Getting latest rathole version..." && \
    RATHOLE_VERSION=$(curl -sL https://api.github.com/repos/rapiz1/rathole/releases | jq -r '.[0].tag_name // "v0.5.0"') && \
    echo "Downloading rathole ${RATHOLE_VERSION} for ${ARCH}..." && \
    RATHOLE_ARCH=$(if [ "$ARCH" = "amd64" ]; then echo "x86_64"; elif [ "$ARCH" = "arm64" ]; then echo "aarch64"; else echo "x86_64"; fi) && \
    RATHOLE_ASSET=$(curl -sL "https://api.github.com/repos/rapiz1/rathole/releases" | jq -r --arg arch "$RATHOLE_ARCH" '.[0].assets[] | select(.name | contains($arch) and (contains("linux-gnu") or contains("linux-musl"))) | .browser_download_url' | head -1) && \
    if [ -z "$RATHOLE_ASSET" ] || [ "$RATHOLE_ASSET" = "null" ]; then \
        echo "Error: Could not find rathole binary for ${ARCH}"; \
        exit 1; \
    fi && \
    echo "Downloading from: $RATHOLE_ASSET" && \
    if echo "$RATHOLE_ASSET" | grep -q "\.zip$"; then \
        curl -L "$RATHOLE_ASSET" -o /tmp/rathole.zip -f && \
        unzip -q /tmp/rathole.zip -d /tmp && \
        rm /tmp/rathole.zip; \
    else \
        curl -L "$RATHOLE_ASSET" -o /tmp/rathole.tar.gz -f && \
        tar -xzf /tmp/rathole.tar.gz -C /tmp && \
        rm /tmp/rathole.tar.gz; \
    fi && \
    find /tmp -name "rathole" -type f -executable -exec mv {} /usr/local/bin/rathole \; && \
    chmod +x /usr/local/bin/rathole && \
    rm -rf /tmp/rathole* && \
    rathole --version || echo "Rathole installed" && \
    echo "Getting latest gost version..." && \
    GOST_VERSION=$(curl -sL https://api.github.com/repos/ginuerzh/gost/releases | jq -r '.[0].tag_name // "v2.11.5"') && \
    echo "Downloading gost ${GOST_VERSION} for ${ARCH}..." && \
    # Query GitHub API for the correct asset URL
    GOST_ASSET=$(curl -sL "https://api.github.com/repos/ginuerzh/gost/releases" | jq -r --arg arch "$ARCH" '.[0].assets[] | select(.name | contains("linux") and contains($arch)) | .browser_download_url' | head -1) && \
    if [ -z "$GOST_ASSET" ] || [ "$GOST_ASSET" = "null" ]; then \
        echo "Error: Could not find gost binary for ${ARCH}"; \
        exit 1; \
    fi && \
    echo "Downloading from: $GOST_ASSET" && \
    if ! curl -L "$GOST_ASSET" -o /tmp/gost-download -f; then \
        echo "Error: Failed to download gost from $GOST_ASSET"; \
        exit 1; \
    fi && \
    if echo "$GOST_ASSET" | grep -q "\.gz$" && ! echo "$GOST_ASSET" | grep -q "\.tar\.gz"; then \
        if ! gunzip /tmp/gost-download; then \
            echo "Error: Failed to gunzip gost"; \
            exit 1; \
        fi && \
        mv /tmp/gost-download /usr/local/bin/gost; \
    elif echo "$GOST_ASSET" | grep -q "\.zip$"; then \
        if ! unzip -q /tmp/gost-download -d /tmp; then \
            echo "Error: Failed to unzip gost"; \
            exit 1; \
        fi && \
        GOST_BIN=$(find /tmp -name "gost" -type f -executable | head -1) && \
        if [ -z "$GOST_BIN" ]; then \
            echo "Error: Could not find gost binary in archive"; \
            exit 1; \
        fi && \
        mv "$GOST_BIN" /usr/local/bin/gost && \
        rm -rf /tmp/gost* /tmp/gost-download; \
    elif echo "$GOST_ASSET" | grep -q "\.tar\.gz$"; then \
        mv /tmp/gost-download /tmp/gost.tar.gz && \
        if ! tar -xzf /tmp/gost.tar.gz -C /tmp; then \
            echo "Error: Failed to extract gost tar.gz"; \
            exit 1; \
        fi && \
        GOST_BIN=$(find /tmp -name "gost" -type f -executable | head -1) && \
        if [ -z "$GOST_BIN" ]; then \
            echo "Error: Could not find gost binary in archive"; \
            exit 1; \
        fi && \
        mv "$GOST_BIN" /usr/local/bin/gost && \
        rm -rf /tmp/gost* /tmp/gost.tar.gz; \
    else \
        mv /tmp/gost-download /usr/local/bin/gost; \
    fi && \
    chmod +x /usr/local/bin/gost && \
    rm -f /tmp/gost-download /tmp/gost.tar.gz && \
    if [ ! -f /usr/local/bin/gost ]; then \
        echo "Error: gost binary not found at /usr/local/bin/gost after installation"; \
        exit 1; \
    fi && \
    echo "Gost installed successfully at /usr/local/bin/gost" && \
    /usr/local/bin/gost -V || echo "Gost version check skipped"

# Stage 3: Python dependencies (cached layer)
FROM base AS deps
WORKDIR /app
COPY requirements.txt .
# Use pip cache if available
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Stage 4: Final image
FROM base
WORKDIR /app

# Copy binaries from binaries stage
COPY --from=binaries /usr/local/bin/rathole /usr/local/bin/rathole
COPY --from=binaries /usr/local/bin/gost /usr/local/bin/gost

# Copy Python dependencies from deps stage
COPY --from=deps /usr/local /usr/local

# Copy application code (changes most frequently)
COPY . .

EXPOSE 8000 443/tcp 443/udp

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
