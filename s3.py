import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
AWS_REGION  = os.getenv("AWS_REGION")


def upload_file(file_obj, file_name: str, content_type: str = "image/jpeg") -> str:
    """Upload a file-like object to S3 and return its public URL."""
    s3.upload_fileobj(
        file_obj,
        BUCKET_NAME,
        file_name,
        ExtraArgs={"ContentType": content_type},
    )
    return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_name}"


def upload_profile_image(file_obj, file_name: str, content_type: str = "image/jpeg") -> str:
    """
    Upload a high-quality profile image (up to 30 MB) to the
    'profile-images/' prefix in S3.  The file is stored exactly as
    received – no re-compression – so the original quality is preserved.
    """
    s3_key = f"profile-images/{file_name}"
    s3.upload_fileobj(
        file_obj,
        BUCKET_NAME,
        s3_key,
        ExtraArgs={
            "ContentType": content_type,
            # Tell browsers / CDNs to cache for 1 year
            "CacheControl": "max-age=31536000, public",
            # Inline display (no forced download)
            "ContentDisposition": "inline",
        },
    )
    return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"