# This Dockerfile used for create SONiC STM docker container for run MARS STM in docker
# This Docker used in STM config: /.autodirect/sw_regression/system/SONIC/MARS/conf/global/MARS_setups_mgr_docker.conf
# SONiC STM docker based on MARS team image: nbu-harbor.gtm.nvidia.com/sonic/sonic_mars_docker
# SONiC STM docker placed in  nbu-harbor.gtm.nvidia.com/sonic/sonic_mars_docker:latest

FROM nbu-harbor.gtm.nvidia.com/mars/mars_docker:latest

RUN pip install virtualenv

RUN mkdir -p /root/pyenv/
RUN virtualenv /root/pyenv/sonic

ENV PYTHONPATH=""
RUN /root/pyenv/sonic/bin/pip install fabric==2.5.0 pathlib retry pyyaml
ENV PYTHONPATH="/opt/ver_sdk"
