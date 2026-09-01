import json
from utils.logger import logger
from utils.aws import get_elb_instance_ids, get_log_file_names, get_s3_link
from utils.notify import send_message


def lambda_handler(event, context):
    # TODO implement
    logger.info(f"event :{str(event)}")
    # logger.info(event.keys())

    s3_logs = event['S3Logs']
    elb_target_healthy_descriptions = event['ElbTargetHealthDescriptions']
    bucket = event['Bucket']
    prefix = event['Prefix']

    logger.info(f"S3 Logs :{str(event)}")
    logger.info(f"ELB Target Healthy Description :{str(elb_target_healthy_descriptions)}")
    logger.info(f"Bucekt :{str(bucket)}")
    logger.info(f"Prefix :{str(prefix)}")

    log_file_names = get_log_file_names(s3_logs=s3_logs)
    instance_ids = get_elb_instance_ids(elb_target_healthy_descriptions=elb_target_healthy_descriptions)
    s3_link = get_s3_link(bucket=bucket, prefix=prefix)

    send_message(
        log_file_names=log_file_names, 
        instance_ids=instance_ids, 
        s3_link=s3_link, 
        bucket=bucket, 
        prefix=prefix
    )
    

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
