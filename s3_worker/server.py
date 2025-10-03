import boto3
from botocore.exceptions import NoCredentialsError
import os
import requests

s3 = boto3.client('s3')

def upload_to_s3(file_obj, filename : str, bucket : str = "mybucket", extra_args : dict = None) -> str:
    try:
        if extra_args:
            s3.upload_fileobj(file_obj, bucket, filename, ExtraArgs=extra_args)
        else:    
            s3.upload_fileobj(file_obj, bucket, filename)
        return f"https://{bucket}.s3.amazonaws.com/{filename}"
    except NoCredentialsError:
        raise RuntimeError("No AWS credentials found.")
    

def download_from_s3(url: str, workdir: str) -> str:
    """
    Downloads a file from S3 to a local path.
    :param filename: The S3 key (e.g., 'videos/myfile.mp4')
    :param local_path: The local file path to save as
    :param bucket: The S3 bucket name
    :return: The local file path
    """
    local_path = os.path.join(workdir, os.path.basename(url))
    
    response = requests.get(url, stream=True)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to download {url}, status={response.status_code}")

    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return local_path  