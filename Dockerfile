FROM python:3.9-alpine

WORKDIR /app
COPY db-backup.py .

RUN apk --update add \
    postgresql \
    python3 \
    py3-pip \
    && pip3 install --upgrade pip \
    && pip3 install awscli==1.32.0 \
    && pip install boto3==1.35.41

CMD ["python", "db-backup.py"]