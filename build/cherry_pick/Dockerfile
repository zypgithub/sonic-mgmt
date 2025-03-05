FROM python:3.10.16

ARG GERRIT_USERNAME=svc_sonic_ver_bot
ARG GERRIT_API_TOKEN
ARG BRANCH=develop

RUN echo "machine git-nbu-sw.nvidia.com" >> /root/.netrc \
    && echo "login ${GERRIT_USERNAME}" >> /root/.netrc \
    && echo "password ${GERRIT_API_TOKEN}" >> /root/.netrc \
    && git clone -b ${BRANCH} \
        "https://git-nbu-sw.nvidia.com/r/a/switchx/sonic/sonic-mgmt" \
        /root/sonic-mgmt
WORKDIR /root/sonic-mgmt
RUN set -e \
    && mkdir -p `git rev-parse --git-dir`/hooks/ \
    && curl -Lo `git rev-parse --git-dir`/hooks/commit-msg \
        https://git-nbu-sw.nvidia.com/r/tools/hooks/commit-msg \
    && chmod +x `git rev-parse --git-dir`/hooks/commit-msg \
    && git status \
    && git log -1 \
    && git remote add upstream https://github.com/sonic-net/sonic-mgmt.git \
    && git config --global user.email "${GERRIT_USERNAME}@nvidia.com" \
    && git config --global user.name "${GERRIT_USERNAME}" \
    && git config --global gitreview.username "${GERRIT_USERNAME}" \
    && git config --global gitreview.port 443 \
    && git config --global gitreview.scheme https \
    && git config --global gitreview.project r/a/switchx/sonic/sonic-mgmt \
    && apt update && apt install -y git-review
ENV GERRIT_USERNAME=${GERRIT_USERNAME} \
    GEERIT_API_KEY=${GERRIT_API_TOKEN}
COPY . /root/workspace
WORKDIR /root/workspace
RUN pip install -r requirements.txt

