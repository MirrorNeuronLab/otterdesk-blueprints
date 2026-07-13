FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates iproute2 nftables w3m \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000660000 sandbox \
    && useradd -M -d /sandbox -u 1000660000 -g sandbox sandbox \
    && install -d -o sandbox -g sandbox /sandbox \
    && ln -s /usr/local/bin/python3 /usr/bin/python3

WORKDIR /sandbox

# MirrorNeuron injects the manifest's pinned skill dependencies into this
# image at bundle preparation time.
