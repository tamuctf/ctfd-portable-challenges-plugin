FROM ctfd/ctfd:mark-3.2.0

RUN pip install PyYML --user --no-cache-dir
ENV PYTHONUNBUFFERED 1 # easier to debug
ENV ACCESS_LOG /var/log/CTFd/access.log
ENV ERROR_LOG /var/log/CTFd/error.log

WORKDIR /opt/CTFd
