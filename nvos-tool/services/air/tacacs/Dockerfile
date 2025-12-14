FROM ubuntu:bionic
 
# Install necessary packages
RUN apt-get update && \
        apt-get install -y tacacs+ && \
        apt-get clean
 
# Copy the TACACS+ configuration file to the container
COPY tac_plus.conf /etc/tacacs+/tac_plus.conf
 
# Expose the default TACACS+ port
EXPOSE 49

CMD ["/usr/sbin/tac_plus", "-C", "/etc/tacacs+/tac_plus.conf", "-G"]