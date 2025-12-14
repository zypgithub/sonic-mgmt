FROM ghcr.io/openconfig/gnmic:0.42.1

USER root
RUN apk add --no-cache bash
WORKDIR /configs
ENV PATH="/app/gnmic:$PATH"

CMD ["-c", "sleep infinity"]