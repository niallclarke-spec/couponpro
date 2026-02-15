import os

import boto3
from botocore.client import Config as BotoConfig

from core.logging import get_logger

logger = get_logger('telethon_session')

SESSION_BASE_DIR = os.environ.get('TELETHON_SESSION_DIR', '/tmp/telethon_sessions')
BUCKET_PREFIX = 'telethon_sessions'


def _get_s3_client():
    access_key = os.environ.get('SPACES_ACCESS_KEY')
    secret_key = os.environ.get('SPACES_SECRET_KEY')
    region = os.environ.get('SPACES_REGION', 'sfo3')

    if not access_key or not secret_key:
        logger.warning("SPACES_ACCESS_KEY / SPACES_SECRET_KEY not set, session persistence disabled")
        return None, None, None

    bucket = os.environ.get('SPACES_BUCKET', 'couponpro-templates')
    endpoint_url = f'https://{region}.digitaloceanspaces.com'

    client = boto3.client(
        's3',
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version='s3v4'),
    )
    return client, bucket, region


def _local_path(tenant_id: str) -> str:
    return os.path.join(SESSION_BASE_DIR, f'{tenant_id}.session')


def _remote_key(tenant_id: str) -> str:
    return f'{BUCKET_PREFIX}/{tenant_id}.session'


def save_session(tenant_id: str) -> bool:
    local = _local_path(tenant_id)
    if not os.path.exists(local):
        logger.warning(f"No local session file to upload for tenant={tenant_id}")
        return False

    client, bucket, _ = _get_s3_client()
    if not client:
        return False

    try:
        key = _remote_key(tenant_id)
        client.upload_file(local, bucket, key)
        logger.info(f"Session uploaded for tenant={tenant_id} -> {key}")
        return True
    except Exception as e:
        logger.exception(f"Failed to upload session for tenant={tenant_id}: {e}")
        return False


def restore_session(tenant_id: str) -> bool:
    client, bucket, _ = _get_s3_client()
    if not client:
        return False

    local = _local_path(tenant_id)
    os.makedirs(SESSION_BASE_DIR, exist_ok=True)

    try:
        key = _remote_key(tenant_id)
        client.download_file(bucket, key, local)
        logger.info(f"Session restored for tenant={tenant_id} <- {key}")
        return True
    except client.exceptions.NoSuchKey:
        logger.info(f"No remote session found for tenant={tenant_id}")
        return False
    except Exception as e:
        logger.exception(f"Failed to restore session for tenant={tenant_id}: {e}")
        return False


def delete_session(tenant_id: str) -> bool:
    local = _local_path(tenant_id)
    if os.path.exists(local):
        try:
            os.remove(local)
            logger.info(f"Local session deleted for tenant={tenant_id}")
        except OSError as e:
            logger.warning(f"Failed to delete local session for tenant={tenant_id}: {e}")

    client, bucket, _ = _get_s3_client()
    if not client:
        return False

    try:
        key = _remote_key(tenant_id)
        client.delete_object(Bucket=bucket, Key=key)
        logger.info(f"Remote session deleted for tenant={tenant_id}")
        return True
    except Exception as e:
        logger.exception(f"Failed to delete remote session for tenant={tenant_id}: {e}")
        return False
