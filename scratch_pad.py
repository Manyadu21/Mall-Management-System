import shutil
from src.main.utility.my_sql_session import get_mysql_connection
from src.main.utility.spark_session import *
import os
from resources.dev import config
from src.main.utility.s3_client_object import *
from src.main.utility.encrypt_decrypt import *

s3_client_provider = S3ClientProvider(decrypt(config.aws_access_key), decrypt(config.aws_secret_key))
s3_client = s3_client_provider.get_client()


import boto3
import traceback
from src.main.utility.logging_config import *


def list_files(s3_client, bucket_name, folder_path):
    print("inside list file")
    try:
        print(folder_path)
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_path)
        if 'Contents' in response:
            logger.info("Total files available in folder '%s' of bucket '%s': %s", folder_path, bucket_name, response)
            files = [f"s3://{bucket_name}/{obj['Key']}" for obj in response['Contents'] if
                     not obj['Key'].endswith('/')]
            return files
        else:
            return []
    except Exception as e:
        error_message = f"Error listing files: {e}"
        traceback_message = traceback.format_exc()
        logger.error("Got this error : %s", error_message)
        print(traceback_message)
        raise


folder_path = "sales_data/"
# list_files(s3_client,config.bucket_name,folder_path)
s3_absolute_file_path = list_files(s3_client, config.bucket_name, folder_path)
logger.info("Absolute path on s3 bucket for csv file %s ", s3_absolute_file_path)

################### Directory will also be available if you use this ###########

# def list_files(self, bucket_name):
#     try:
#         response = self.s3_client.list_objects_v2(Bucket=bucket_name)
#         if 'Contents' in response:
#             files = [f"s3://{bucket_name}/{obj['Key']}" for obj in response['Contents']]
#             return files
#         else:
#             return []
#     except Exception as e:
#         print(f"Error listing files: {e}")
#         return []


# try:
#     response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_path)
#     if 'Contents' in response:
#         logger.info("Total files available in folder '%s' of bucket '%s': %s", folder_path, bucket_name, response)
#         files = [f"s3://{bucket_name}/{obj['Key']}" for obj in response['Contents'] if
#                  not obj['Key'].endswith('/')]
#         return files
#     else:
#         return []
#
# try:
#     response = s3_client.list_objects_v2(Bucket=bucket_name)
#     if 'Contents' in response:
#         logger.info("Total file available in bucket %s", response)
#         files = [f"s3://{bucket_name}/{obj['Key']}" for obj in response['Contents'] if
#                  not obj['Key'].endswith('/')]
#         return files
#     else:
#         return []
