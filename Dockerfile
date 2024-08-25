FROM ctfd/ctfd:3.7.3
RUN pip install PyYML --no-cache-dir
ENV PYTHONUNBUFFERED 1 # easier to debug
ENV ACCESS_LOG /var/log/CTFd/access.log
ENV ERROR_LOG /var/log/CTFd/error.log

WORKDIR /opt/CTFd
