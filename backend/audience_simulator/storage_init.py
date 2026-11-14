"""Create the private artifact bucket before API and worker start."""

import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings


def main():
    cfg = settings()
    client = boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
    )
    for attempt in range(30):
        try:
            client.create_bucket(Bucket=cfg.s3_bucket)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                return
            if attempt == 29:
                raise
        except BotoCoreError:
            if attempt == 29:
                raise
        time.sleep(1)


if __name__ == "__main__":
    main()
