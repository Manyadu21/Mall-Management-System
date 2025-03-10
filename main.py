# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.


# def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    # print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.


# Press the green button in the gutter to run the script.
# if __name__ == '__main__':
   # print_hi('Kalpna')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/


# import logging
import os
import shutil
# import sys
# import pandas
import spark
from pip._internal.utils import datetime
from pyspark.sql.connect.functions import concat_ws, lit
from pyspark.sql.functions import expr
from pyspark.sql.types import *
# (StructField, IntegerType)

from resources.dev import config
from src.main.delete.local_file_delete import delete_local_file
from src.main.download.aws_file_download import S3FileDownloader
from src.main.move.move_files import *
from src.main.read.aws_read import *
from src.main.read.database_read import DatabaseReader
from src.main.transformations.jobs.customer_mart_sql_transform_write import customer_mart_calculation_table_write
from src.main.transformations.jobs.sales_mart_sql_transform_write import sales_mart_calculation_table_write
from src.main.upload.upload_to_s3 import UploadToS3
from src.main.utility.encrypt_decrypt import *
from src.main.utility.logging_config import *
from src.main.utility.s3_client_object import *
from src.main.utility.my_sql_session import *
from src.main.read import *
from src.main.write.parquet_writer import ParquetWriter

# GET S3 CLIENT
aws_access_key = config.aws_access_key
aws_secret_key = config.aws_secret_key

s3_client_provider = S3ClientProvider(decrypt(aws_access_key), decrypt(aws_secret_key))
s3_client = s3_client_provider.get_client()

# using s3_client for s3 operation
response = s3_client.list_buckets()
logger.info("List of Buckets: %s", response['Buckets'])

# check if local directory has already a file if file is there then check if some file is present
# in the staging area with status as A. if so then don`t delete and try to re-run
# Else give an error and not process the next file
csv_files = [file for file in os.listdir(config.local_directory) if file.endswith(".csv")]
connection = get_mysql_connection()
cursor = connection.cursor()
total_csv_files = []
if csv_files:
    for file in csv_files:
        total_csv_files.append(file)
    statement = f"select distinct file_name from " \
                f"{config.database_name}.{config.customer_table_name}" \
                f"mall_management.product_staging_table " \
                f"where file_name in ({str(total_csv_files)[1:-1]}) and status = 'I' "
    logger.info(f"dynamically statement created: {statement}")
    cursor.execute(statement)
    data = cursor.fetchall()
    if data:
        logger.info("Your last run was failed please check ")
    else:
        logger.info("No record match ")

else:
    logger.info("Last run was successful!!!")

try:
    s3_reader = S3Reader()
    # Bucket name should come from table
    folder_path = config.s3_source_directory
    s3_absolute_file_path = s3_reader.list_files(s3_client,
                                                 config.bucket_name,
                                                 folder_path=folder_path)
    logger.info(("Absolute path on s3 bucket for csv file %s ", s3_absolute_file_path))
    if not s3_absolute_file_path:
        logger.info(f"No files available at {folder_path}")
        raise Exception("No Data available to process ")

except Exception as e:
    logger.error("Exited with error :- %s ", e)
    raise e

# [ 's3://minor_project/sales_data/extra_column_data.csv', 's3://minor_project/sales_data/file5.json,'continue as well]


bucket_name = config.bucket_name
local_directory = config.local_directory

prefix = f"s3://{bucket_name}/"
file_paths = [url[len(prefix):] for url in s3_absolute_file_path]
logging.info("File path available on s3 under %s bucket and folder name is %s", bucket_name, file_paths)
logging.info(f"File path available on s3 under {bucket_name} bucket and folder name is {file_paths}")
try:
    downloader = S3FileDownloader(s3_client, bucket_name, local_directory)
    downloader.download_files(file_paths)
except Exception as e:
    logger.error("File download error : %s ", e)
    sys.exit()

# Get a list of all files in the local directory
all_files = os.listdir(local_directory)
logger.info(f"List of files present at my local directory after download {all_files}")

# Filter files with ".csv" in their names and create absolute paths
if all_files:
    csv_files = []
    error_files = []
    for files in all_files:
        if files.endswith(".csv"):
            csv_files.append(os.path.abspath(os.path.join(local_directory, files)))
        else:
            error_files.append(os.path.abspath(os.path.join(local_directory, files)))

    if not csv_files:
        logger.error("No csv data available to process the request")
        raise Exception("No csv data available to process the request")

else:
    logger.error("There is no data to process")
    raise Exception("There is no data to process")

# Make csv lines convert into a list of comma separated

# csv_files = str(csv_files)[1:-1]
logger.info("**************** Listing the file **************")
logger.info("List of csv files that need to be processed %s", csv_files)

logger.info("********** Creating spark session ****************")

spark = spark.session()

logger.info("************* Spark session created *************")

# check the required column in the schema of csv file
# if not required columns keep it in a list of error files
# else union all the data into one dataframe

logger.info("************* Checking schema for data loaded in s3 *************")

correct_files = []
for data in csv_files:
    data_schema = spark.read.format("csv") \
        .option("header", "true") \
        .load(data).columns
    logger.info(f"schema for the{data} is {data_schema}")
    logger.info(f"Mandatory columns schema is {config.mandatory_columns}")
    missing_columns = set(config.mandatory_columns) - set(data_schema)
    logger.info(f"Missing columns are {missing_columns}")

    if missing_columns:
        error_files.append(data)
    else:
        logger.info(f"No missing colum for the {data} ")
        correct_files.append(data)

logger.info(f"************** List of correct Files **************")
logger.info(f"***************** List of error files ******************")
logger.info("************** Moving error data to error directory if any ****************")

# move the data to error directory on local
error_folder_local_path = config.error_folder_path_local
if error_files:
    for file_path in error_files:
        if os.path.exists(file_path):
            file_name = os.path.basename(file_path)
            destination_path = os.path.join(error_folder_local_path, file_name)

            shutil.move(file_path, destination_path)
            logger.info(f"Moved '{file_name}' from s3 file path to '{destination_path}',")

            source_prefix = config.s3_source_directory
            destination_prefix = config.s3_error_directory

            message = move_s3_to_s3(s3_client, config.bucket_name, source_prefix, destination_prefix, file_name)
            logger.info(f"{message}")
        else:
            logger.error(f"'{file_path}' does not exist. ")
else:
    logger.info("**************** There is no errorfiles available at our dataset *******************")

# Additional columns needs to be taken card of
# determine extra columns

# Before running the process
# stage table needs to be updated with status as Active(A) or Inactive(I)
logger.info(f"************Updating the product_staging-table that we have started the process ************")
insert_statements = []
db_name = config.database_name
current_date = (datetime.datetime.now())
formatted_date = current_date.strftime("%Y-%m-%d  %H:%M:%s ")
if correct_files:
    for file in correct_files:
        filename = os.path.basename(file)
        statements = f"INSERT INTO {db_name},{config.product_staging_table} " \
                     f"(file_name, file_location, created_date, status) " \
                     f"VALUES ('{filename}', '{filename}', '{formatted_date}', 'A')"

        insert_statements.append(statements)
    logger.info(f"Insert statement created for staging table ----{insert_statements} ")
    logger.info("***************** Connecting with MySql server **************")
    connection = get_mysql_connection()
    cursor = connection.cursor()
    logger.info("***************** MySql server connected successfully *****************")
    for statement in insert_statements:
        cursor.execute(statement)
        connection.commit()
    cursor.close()
    connection.close()
else:
    logger.error("*************** There is no files to process **********")
    raise Exception("******************* No Data available with correct files *****************")

logger.info("*************** Staging table updated successfully **************")

logger.info("************* Fixing extra column coming from source *************")

schema = StructType([
    StructField("customer_id", IntegerType(), True),
    StructField("store_id", IntegerType(), True),
    StructField("Product_name", StringType(), True),
    StructField("sales_data", DataType(), True),
    StructField("sales_person_id", IntegerType(), True),
    StructField("price", FloatType(), True),
    StructField("quality", IntegerType(), True),
    StructField("total_cost", FloatType(), True),
    StructField("additional_column", StringType(), True),
])

# connecting with DatabaseReader
database_client = DatabaseReader(config.url, config.properties)
logger.info("*********** Creating empty dataframes **********")
final_df_to_process = database_client.create_dataframe(spark, "empty_df_create_table")

# final_df_to_process = spark.createDataframe([], schema=schema)
# Create a new column with concatenated valuedof extra columns
for data in correct_files:
    data_df = spark.read.format("csv") \
        .option("header", "true") \
        .option("inferschema", "true") \
        .load(data)
    data_schema = data_df.columns
    extra_columns = list(set(data_schema) - set(config.mandatory_columns))
    logger.info(f"Extra columns present at source is {extra_columns}")
    if extra_columns:
        data_df = data_df.withColumn("additional_column", concat_ws(", ", *extra_columns)) \
            .select("customer_id", "store_id", "product_name", "sales_date", "sales_person_id",
                    "price", "quality", "total_cost", "additional_column")
        logger.info(f"processed {data} and added 'addititonal_column'")
    else:
        data_df = data_df.withColumn("additional_column", lit(None)) \
            .select("customer_id", "store_id", "product_name", "sales_date", "sales_person_id",
                    "price", "quality", "total_cost", "additional_column")

    final_df_to_process = final_df_to_process.union(data_df)
# find_df_to_process = data_df
logger.info("*********** Final Dataframe from source which will be going to processing ***********")
final_df_to_process.show()

# enrich the data from all dimension table
# also create a datamart for sales_team and their incentive, address and all
# another datamart for customer who bought how much each day of month
# for every month there should be a file and inside that
# there should be a store_id segrigation
# read the data from parquet and generate a csv file
# in which there will be a sales_person_name, sales_person_store_id
# sales_person_total_billing_done_for_each_month, total_incentive

# connecting with databaseReader
database_client = DatabaseReader(config.url, config.properties)
# creating df for all tables
# customer table
logger.info("************ Loading customer table into customer_table_df *************")
customer_table_df = database_client.create_dataframe(spark, config.customer_table_name)
# product table
logger.info("************ Loading customer table into product_table_df *************")
product_table_df = database_client.create_dataframe(spark, config.product_table)

# product_staging_table table
logger.info("************ Loading customer table into product_staging_table_df *************")
product_staging_table_df = database_client.create_dataframe(spark, config.product_staging_table)

# sales_team table
logger.info("************ Loading customer table into sales_team_table_df *************")
sales_team_table_df = database_client.create_dataframe(spark, config.sales_team_table)

# store table
logger.info("************ Loading customer table into store_table_df *************")
store_table_df = database_client.create_dataframe(spark, config.store_table)

s3_customer_store_sales_df_join = dimensions_table_join(final_df_to_process, customer_table_df, store_table_df,
                                                        sales_team_table_df)

# Final enriched data
logger.info("************** Final Enriched data ***********")
s3_customer_store_sales_df_join.show()

# write the customer data into customer data mart in parquet format
# file will be written to local first
# write reporting data into MySql also
logger.info("*********** Write the data into customer data mart ************")
final_customer_data_mart_df = s3_customer_store_sales_df_join \
    .select("ct.customer_id",
            "ct.first_name", "ct.last_name", "ct.address", "ct.pincode", "phone_number",
            "sales_date", "total_cost")
logger.info("************ Final data for customer data mart **************")
final_customer_data_mart_df.show()

parquet_writer = ParquetWriter("overwrite", "parquet")
parquet_writer.dataframe_writer(final_customer_data_mart_df, config.customer_data_mart_local_file)

logger.info(f"********* customer data written to local disk at {config.customer_data_mart_local_file}")

# move data on s3 bucket for customer_data_mart
logger.info(f"*************** data movement from local to s3 for customer data mart **********")
s3_uploader = UploadToS3(s3_client)
s3_directory = config.s3_customer_datamart_directory
message = s3_uploader.upload_to_s3(s3_directory, config.bucket_name, config.customer_data_mart_local_file)
logger.info(f"{message}")

# sales_team data mart
logger.info("************ Write the data into sales_team-data_mart ***************")
final_sales_team_data_mart_df = s3_customer_store_sales_df_join \
    .select("store_id",
            "sales_person_id", "sales_person_first_name", "sales_person_last_name", "store_manager_name",
            "manager_id", "is_manager", "sales_person_address", "sales_person_pincode",
            "sales_date", "total_cost", expr("SUBSTRING(sales_date, 1, 7) as sales_month"))

logger.info("************** Final data for sales team Data Mart *****************")
final_sales_team_data_mart_df.show()
parquet_writer.dataframe_writer(final_sales_team_data_mart_df, config.sales_team_data_mart_local_file)

logger.info(f"************ salesteam data wrotem to local disk at {config.sales_team_data_mart_local_file}")


# Move data on s3 bucket for sales_data_mart
s3_directory = config.s3_sales_datamart_directory
message = s3_uploader.upload_to_s3(s3_directory, config.bucket_name, config.sales_team_data_mart_local_file)

logger.info(f"{message}")

# also writing the data into partitions
final_sales_team_data_mart_df.write.format("parquet")\
    .option("header", "true") \
    .mode("overwrite") \
    .partitionBy("sales_month", "store_id") \
    .option("path", config.sales_team_data_mart_partitioned_local_file) \
    .save()

# Move data on s3 for partitioned folder
s3_prefix = "sales_partitioned_data_mart"
current_epoch = int(datetime.datetime.now().timestamp()) *1000
for root, dirs, files in os.walk(config.sales_team_data_mart_partitioned_local_file):
    for file in files:
        print(file)
        local_file_path = os.path.join(root, file)
        relative_file_path = os.path.relpath(local_file_path, config.sales_team_data_mart_partitioned_local_file)
        s3_key = f"{s3_prefix}/{current_epoch}/{relative_file_path}"
        s3_client.upload_file(local_file_path, config.bucket_name, s3_key)


# calculation for customer mart
# find out the customer total purchase every month
# write the data into MySql table
logger.info("******** calculating customer every month puchsed amount *********")
customer_mart_calculation_table_write(final_customer_data_mart_df)
logger.info("******* calculation of customer mart is done and written into the table **********")

# calculation for sales team mart
# find out the total sales done by each and every person evry month
# give the top performer 1% incentive of total sales of the month
# Rest sales person will get nothing
# write the data in mySql table

logger.info("********* Calculating sales every month billed amount **********")

sales_mart_calculation_table_write(final_sales_team_data_mart_df)

logger.info("*********** Calculation of sales mart is done and written into the table ************")


# LLLLLLLLLLLLLlAST SSSSSSSSSSSTEP
# move the file on s3 into processed folder and delete the local files
source_prefix = config.s3_source_directory
destination_prefix = config.s3_processed_directory
message = move_s3_to_s3(s3_client, config.bucket_name, source_prefix, destination_prefix)
logger.info(f"{message}")


logger.info("************ Deleting sales data from local **************")
delete_local_file(config.local_directory)
logger.info("*********** deleted sales data from local **************")


logger.info("************ Deleting customer_data_mart_local_file from local **************")
delete_local_file(config.customer_data_mart_local_file)
logger.info("*********** deleted customer_data_mart_local_file from local **************")


logger.info("************ Deleting sales_team_data_mart_local_file from local **************")
delete_local_file(config.sales_team_data_mart_local_file)
logger.info("*********** deleted sales_team_data_mart_local_file from local **************")


logger.info("************ Deleting sales_team_data_mart_partitioned_local_file from local **************")
delete_local_file(config.sales_team_data_mart_partitioned_local_file)
logger.info("*********** deleted sales_team_data_mart_partitioned_local_file from local **************")

# update the status of staging table
update_statements =[]
if correct_files:
    for file in correct_files:
        filename = os.path.basename(file)
        statements = f"UPDATE {db_name}.{config.product_staging_table} " \
                     f" SET STATUS = 'I', updated_date = '{formatted_date}' " \
                     f"WHERE file_name = '{filename}'"

        update_statements.append(statements)
    logger.info(f"Updated staement created for staging table ---- {update_statements}")
    logger.info("******** CONNECTING WITH MYSQL SERVER ************")
    connection = get_mysql_connection()
    cursor = connection.cursor()
    logger.info("*************** MySql server connected successfully *************")
    for statement in update_statements:
        cursor.execute(statement)
        connection.commit()
    cursor.close()
    connection.close()
else:
    logger.info("********** There is some error in process in between ************")
    sys.exit()


input("Press enter to terminate.")

