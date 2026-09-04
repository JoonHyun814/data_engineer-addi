from utils.logger import logger


def get_log_file_names(s3_logs: dict) -> str:
    
    file_names = list()
    for content in s3_logs['Contents']:
        file_name = content['Key'].split('/')[-1]
        file_names.append(file_name)

    logger.info(f"Log Files: {str(file_names)}")

    return ', '.join(file_names)


def get_elb_instance_ids(elb_target_healthy_descriptions: str):
    instance_ids = list()

    for elb_target_healthy_description in elb_target_healthy_descriptions['TargetHealthDescriptions']:
        if elb_target_healthy_description['TargetHealth']['State'] == 'healthy':
            instance_id = elb_target_healthy_description['Target']['Id']
            instance_ids.append(instance_id)
    
    logger.info(f"Instance Ids: {str(instance_ids)}")

    return ', '.join(instance_ids)

def get_s3_link(bucket: str, prefix: str) -> str:       
    s3_link = f"https://ap-northeast-2.console.aws.amazon.com/s3/buckets/{bucket}?region=ap-northeast-2&bucketType=general&prefix={prefix}/"  
    return s3_link

