FROM debian:buster

ENV APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=DontWarn
ARG VM_USER
ARG VM_PASSWORD
# Update sources.list for Debian 10 archive repositories
RUN echo "deb http://archive.debian.org/debian buster main" > /etc/apt/sources.list && \
    echo "deb http://archive.debian.org/debian-security buster/updates main" >> /etc/apt/sources.list && \
    echo "deb http://archive.debian.org/debian buster-updates main" >> /etc/apt/sources.list
RUN apt-get update

# Install required packages
RUN apt-get install -y libpcre3-dev apt-transport-https ca-certificates curl wget logrotate \
    libc-ares2 libjson-c3 vim systemd procps libreadline7 gnupg2 lsb-release apt-utils openssh-server \
    sudo iproute2 net-tools libaio1 python-dev python-setuptools initscripts mlocate libtinfo-dev \
    less gcc make libssl-dev sqlite3 libsqlite3-dev python-lxml libxml2-dev lldpad vlan tcpdump telnet \
    isc-dhcp-client isc-dhcp-server sqlite fping git bridge-utils iperf3 autoconf linuxptp arping \
    python-pip python-scapy python3-pip tcpreplay snmp ethtool traceroute radvd supervisor && apt-get clean

RUN pip install remotely==0.2.0 pyftpdlib==1.5.6 tftpy==0.8.2
RUN pip3 install daemonize==2.5.0 scapy==2.4.0

#Install FRR
RUN curl -s https://deb.frrouting.org/frr/keys.asc | apt-key add -
RUN echo deb https://deb.frrouting.org/frr $(lsb_release -s -c) frr-8 | tee -a /etc/apt/sources.list.d/frr.list
RUN apt-get update
RUN apt-get install -y frr frr-pythontools
ADD docker-start /usr/sbin/docker-start
RUN sed -i 's/bgpd=no/bgpd=yes/g' /etc/frr/daemons
RUN sed -i 's/bfdd=no/bfdd=yes/g' /etc/frr/daemons

RUN apt install -y teamd
# Configure remote connection details
RUN sed -i 's/UsePAM yes/UsePAM no/g' /etc/ssh/sshd_config
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config
RUN echo "${VM_USER}:${VM_PASSWORD}" | chpasswd
RUN echo "root   ALL=(ALL)       ALL" >> /etc/sudoers
RUN ssh-keygen -t dsa -f /etc/ssh/ssh_host_dsa_key

RUN git clone --branch v5.07 --depth 1 https://github.com/sflow/sflowtool.git
WORKDIR sflowtool
RUN ./boot.sh && ./configure && make && make install

RUN mkdir /var/run/sshd
EXPOSE 22

## configure lldpad to automatically restart on failure with supervisor
RUN mkdir -p /etc/supervisor/conf.d && \
    echo "[program:lldpad]" > /etc/supervisor/conf.d/lldpad.conf && \
    echo "command=lldpad" >> /etc/supervisor/conf.d/lldpad.conf && \
    echo "autorestart=true" >> /etc/supervisor/conf.d/lldpad.conf && \
    echo "startretries=3" >> /etc/supervisor/conf.d/lldpad.conf && \
    echo "startsecs=10" >> /etc/supervisor/conf.d/lldpad.conf && \
    echo "starttime=30" >> /etc/supervisor/conf.d/lldpad.conf && \
    echo "stopsignal=TERM" >> /etc/supervisor/conf.d/lldpad.conf

ENTRYPOINT ["/usr/sbin/docker-start"]
