ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

ARG BUILD_VERSION
ARG BUILD_REF
ARG BUILD_DATE
ENV BUILD_VERSION=${BUILD_VERSION}
ENV BUILD_REF=${BUILD_REF}
ENV BUILD_DATE=${BUILD_DATE}

COPY config.yaml /app/config.yaml

# System deps (Python + build tools + USB)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    bash \
    jq \
    git \
    libusb \
    libusb-dev \
    build-base \
    linux-headers

# Create venv and upgrade tooling inside it
RUN python3 -m venv "${VIRTUAL_ENV}" && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# Python deps (installed into venv)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install rfcat / rflib (pin for reproducible builds)
# Set RFCAT_REF to a tag/commit when you cut releases.
ARG RFCAT_REF=master
RUN git clone https://github.com/atlas0fd00m/rfcat.git /tmp/rfcat && \
    cd /tmp/rfcat && git checkout "${RFCAT_REF}" && \
    pip install --no-cache-dir /tmp/rfcat && \
    rm -rf /tmp/rfcat

# App
COPY src /app/src

# Add-on start script
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
