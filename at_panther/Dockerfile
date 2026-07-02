FROM registry.gitlab.com/docker_point/at-panther:latest

USER root

COPY run.sh /run.sh
COPY main.py /app/main.py
RUN chmod +x /run.sh

CMD ["/run.sh"]
