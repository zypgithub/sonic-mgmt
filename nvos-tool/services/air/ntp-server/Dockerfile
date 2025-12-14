FROM debian:stable-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      chrony tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY chrony.conf /etc/chrony/chrony.conf
EXPOSE 123/udp
CMD ["chronyd", "-d", "-f", "/etc/chrony/chrony.conf"]