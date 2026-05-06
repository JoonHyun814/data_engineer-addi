from sync import SyncManager
from utils.logger import logger


def lambda_handler(event, context):
    logger.info(f"Event: {event}")

    db_cluster_name = event['db_cluster_name']
    db_name         = event['db_name']
    table_name      = event['table_name']
    watermark_col   = event.get('watermark_column', 'id')
    glue_db         = event['glue_db']
    glue_table      = event['glue_table']
    s3_bucket       = event.get('s3_bucket', 'ptbwa-da')
    s3_prefix       = event.get('s3_prefix', f'prod/{glue_table}')

    sync = SyncManager(db_cluster_name=db_cluster_name, db_name=db_name)
    try:
        sync.run(
            table_name=table_name,
            watermark_col=watermark_col,
            glue_db=glue_db,
            glue_table=glue_table,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
        )
    finally:
        sync.disconnect()
