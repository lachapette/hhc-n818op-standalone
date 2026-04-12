FROM python:3.11-alpine
ARG INSTALL_FOLDER_CLIENT=${INSTALL_FOLDER_CLIENT}
ARG LOGGING=/var/log
WORKDIR ${INSTALL_FOLDER_CLIENT}
ENV PYTHONPATH=${INSTALL_FOLDER_CLIENT}

RUN apk add --no-cache tzdata && python -m pip install --no-cache-dir --upgrade pip

# Create log and pid directories/files with proper permissions
RUN mkdir -p ${LOGGING} && touch ${LOGGING}/daemon_hhc_n818op.log && chmod 666 ${LOGGING}/daemon_hhc_n818op.log && \
    mkdir -p /run && touch /run/hhc_n818op_d.pid && chmod 666 /run/hhc_n818op_d.pid

COPY daemon_hhc_n818op ${INSTALL_FOLDER_CLIENT}/daemon_hhc_n818op
COPY docker/bin/ps.sh /usr/local/bin/ps.sh

RUN chmod 755 /usr/local/bin/ps.sh && python -m pip install --no-cache-dir requests ruamel.yaml pytz meross-iot

ENTRYPOINT ["sh", "-c", "export PYTHONPATH=$(pwd) && python daemon_hhc_n818op/hhc_n818op_standalone_d.py"]
