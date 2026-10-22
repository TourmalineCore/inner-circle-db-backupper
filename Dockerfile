FROM python:3.9-alpine

WORKDIR /app
COPY db-backup.py .

ARG TARGETARCH

RUN apk --update add \
    curl \
    postgresql \
    python3 \
    py3-pip \
    && pip3 install --upgrade pip \
    && pip3 install awscli==1.32.0 \
    && pip install boto3==1.35.41

# install kubectl https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/#install-kubectl-binary-with-curl-on-linux
# curl -Lo - follow redirects and write to file
# chmod +x - make file executable
RUN curl -Lo kubectl https://dl.k8s.io/release/v1.30.0/bin/linux/$TARGETARCH/kubectl && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin

CMD ["python", "db-backup.py"]