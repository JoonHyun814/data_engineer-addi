from sync import FullRefreshManager
from utils.logger import logger


def lambda_handler(event, context):
    logger.info(f"Event: {event}")

    secret_name = event['secret_name']
    db_name     = event['db_name']
    table_name  = event['table_name']
    glue_db     = event['glue_db']
    glue_table  = event['glue_table']
    s3_bucket   = event['s3_bucket']
    s3_prefix   = event['s3_prefix']

    manager = FullRefreshManager(secret_name=secret_name, db_name=db_name)
    try:
        manager.run(
            table_name=table_name,
            glue_db=glue_db,
            glue_table=glue_table,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
        )
    finally:
        manager.disconnect()
