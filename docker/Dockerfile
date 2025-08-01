FROM mysql:8.0-debian
LABEL org.opencontainers.image.authors="cc3630test@gmail.com"

RUN apt-get update && \
 apt-get install -y zip psmisc python3 python3-boto3

WORKDIR /app
ADD . /app

VOLUME /backup

RUN chmod 777 /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
