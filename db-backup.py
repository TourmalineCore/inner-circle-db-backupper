import base64
import json
import os
import subprocess
import logging
import pyzipper
from datetime import datetime, UTC
import boto3

temp_directory_for_backups = "/tmp/inner-circle"
namespace = os.getenv("NAMESPACE")
password = os.getenv("INNER_CIRCLE_DB_BACKUP_PASSWORD")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s]: %(message)s",
    datefmt="%Y-%m-%dT%H-%M-%S",
)


def run(cmd, environment=None):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment
    )
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"Command failed: {stderr}")

    return stdout


def get_db_credentials():
    logging.info("Retrieving deployments list")
    deployments = json.loads(
        run(["kubectl", "get", "deployments", "-n", namespace, "-o", "json"])
    )
    logging.info("Successfully retrieved deployments list")

    logging.info("Retrieving secrets list")
    secrets_data = json.loads(
        run(["kubectl", "get", "secrets", "-n", namespace, "-o", "json"])
    )
    logging.info("Successfully retrieved secrets list")

    secrets = {item["metadata"]["name"]: item for item in secrets_data.get("items", [])}

    references = set()

    for deployment in deployments.get("items", []):
        deployment_name = deployment["metadata"]["name"]

        container = deployment["spec"]["template"]["spec"]["containers"][0]

        for env_from in container.get("envFrom", []):
            if secret_ref := env_from.get("secretRef"):
                references.add(
                    (
                        deployment_name,
                        container["name"],
                        secret_ref["name"],
                    )
                )

    connection_strings = []

    for deployment, container, secret_name in sorted(references):
        secret = secrets.get(secret_name)

        encoded_value = secret.get("data", {}).get(
            "ConnectionStrings__DefaultConnection"
        )

        if not encoded_value:
            continue

        connection_strings.append(base64.b64decode(encoded_value).decode("utf-8"))
    logging.info(f"Successfully retrieved {len(connection_strings)} connection strings")

    return connection_strings


def upload_to_s3(backup_filename):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("INNER_CIRCLE_BACKUPS_BUCKET_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv(
            "INNER_CIRCLE_BACKUPS_BUCKET_SECRET_ACCESS_KEY"
        ),
        endpoint_url=os.getenv("INNER_CIRCLE_BACKUPS_BUCKET_ENDPOINT"),
    )

    bucket_name = os.getenv("INNER_CIRCLE_BACKUPS_BUCKET_NAME")

    logging.info(
        'Uploading backup "%s" to S3 bucket "%s"', backup_filename, bucket_name
    )
    try:
        with open(backup_filename, "rb") as data:
            s3.upload_fileobj(data, bucket_name, backup_filename)
            logging.info('Successfully uploaded backup "%s" to S3', backup_filename)
    except Exception as err:
        logging.error(f"Failed to upload backup: {err}")
        raise


def create_db_backup(database_host, database_username, database_password, database_name):
    env = {}
    env["PGPASSWORD"] = database_password
    logging.info(f"Creating {database_name} database backup")
    backup_filename = f'{namespace}-{database_name}-{datetime.strftime(datetime.now(UTC), "%Y-%m-%dT%H-%M-%S")}.backup'

    if not os.path.exists(temp_directory_for_backups):
        os.mkdir(temp_directory_for_backups)

    try:
        run(["pg_dump", "-h", database_host, "-U", database_username, "--encoding", "UTF8", "--format", "plain",
              "--file", f"{temp_directory_for_backups}/{backup_filename}", database_name, ],env)
        logging.info(f"Successfuly created {database_name} backup")
    except Exception as err:
        logging.error(f"Failed to create {database_name} database backup: {err}")
        raise


def main():
    connection_strings = get_db_credentials()

    for connection_string in connection_strings:
        db_connection = dict(
            item.split("=", 1) for item in connection_string.split(";")
        )

        create_db_backup(
            db_connection["Host"],
            db_connection["Username"],
            db_connection["Password"],
            db_connection["Database"],
        )

        archive_name = f'{datetime.strftime(datetime.now(UTC), "%Y-%m-%dT%H-%M-%S")}-{namespace}-db-backups.zip'

    if not len(os.listdir(temp_directory_for_backups)) == 0:
        with pyzipper.AESZipFile(archive_name, "w", compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES) as archive:
            archive.setpassword(password.encode("UTF8"))

            for root, _, files in os.walk(temp_directory_for_backups):
                for file in files:
                    archive.write(f"{root}/{file}", file)

    upload_to_s3(archive_name)


if __name__ == "__main__":
    main()
