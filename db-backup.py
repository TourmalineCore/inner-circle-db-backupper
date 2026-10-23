import base64
import json
import os
import subprocess
import logging
import shutil
from datetime import datetime
import boto3

temp_directory_for_backups = "/tmp/inner-circle"
namespace = os.getenv("NAMESPACE")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s]: %(message)s",
    datefmt="%Y-%m-%dT%H-%M-%S",
)

def run(cmd):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = process.communicate()

    return stdout

def get_db_credentials():

    deployments = json.loads(run(["kubectl", "get", "deployments", "-n", namespace, "-o", "json"]))
    
    secrets_data = json.loads(run(["kubectl", "get", "secrets", "-n", namespace, "-o", "json"]))

    secrets = {
        item["metadata"]["name"]: item
        for item in secrets_data.get("items", [])
    }

    references = set()

    for deployment in deployments.get("items", []):
        deployment_name = deployment["metadata"]["name"]

        container = deployment["spec"]["template"]["spec"]["containers"][0]

        for env_from in container.get("envFrom", []):
            if secret_ref := env_from.get("secretRef"):
                references.add((
                    deployment_name,
                    container["name"],
                    secret_ref["name"],
                ))

    connection_strings = []

    for deployment, container, secret_name in sorted(references):
        secret = secrets.get(secret_name)

        encoded_value = (
            secret.get("data", {})
            .get("ConnectionStrings__DefaultConnection")
        )

        if not encoded_value:
            continue

        connection_strings.append(base64.b64decode(encoded_value).decode("utf-8"))

    return connection_strings

def upload_to_s3(backup_filename):
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('INNER_CIRCLE_BACKUPS_BUCKET_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('INNER_CIRCLE_BACKUPS_BUCKET_SECRET_ACCESS_KEY'),
        endpoint_url=os.getenv('INNER_CIRCLE_BACKUPS_BUCKET_ENDPOINT'),
    )

    bucket_name = os.getenv('INNER_CIRCLE_BACKUPS_BUCKET_NAME')

    with open(backup_filename, "rb") as data:
        s3.upload_fileobj(data, bucket_name, backup_filename)

def create_db_backup(database_host, database_username, database_password, database_name):
    backup_filename = f'{namespace}-{database_name}-{datetime.strftime(datetime.utcnow(), "%Y-%m-%dT%H-%M-%S")}.backup'
    
    if not os.path.exists(temp_directory_for_backups):
        os.mkdir(temp_directory_for_backups)

    os.system(f'PGPASSWORD={database_password} pg_dump -h {database_host} -U {database_username} --encoding UTF8 --format plain {database_name} > {temp_directory_for_backups}/{backup_filename}')

def main():
    connection_strings = get_db_credentials()
  
    for connection_string in connection_strings:
        db_connection = dict(item.split("=", 1) for item in connection_string.split(";"))

        create_db_backup(db_connection['Host'], db_connection['Username'], db_connection['Password'], db_connection['Database'])

        archive_name = f'{datetime.strftime(datetime.utcnow(), "%Y-%m-%dT%H-%M-%S")}-{namespace}-inner-circle-db-backups'

    if not len(os.listdir(temp_directory_for_backups)) == 0:
        shutil.make_archive(archive_name, 'zip', temp_directory_for_backups)

        upload_to_s3(archive_name + ".zip")

if __name__ == "__main__":
  main()