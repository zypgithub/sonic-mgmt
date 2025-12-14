FROM debian:stable-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      dnsmasq nginx supervisor ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/tftpboot /usr/share/nginx/html /var/log/supervisor

COPY dnsmasq.conf /etc/dnsmasq.d/ztp.conf
COPY nginx.conf   /etc/nginx/nginx.conf

RUN printf "%s\n" \
"[supervisord]" \
"nodaemon=true" \
"" \
"[program:dnsmasq]" \
"command=/usr/sbin/dnsmasq -k --conf-file=/etc/dnsmasq.d/ztp.conf" \
"autorestart=true" \
"" \
"[program:nginx]" \
"command=/usr/sbin/nginx -g 'daemon off;'" \
"autorestart=true" \
> /etc/supervisor/conf.d/supervisord.conf

EXPOSE 67/udp 69/udp 80/tcp
VOLUME ["/var/lib/tftpboot", "/usr/share/nginx/html"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]