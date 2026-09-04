import datetime
import dateutil
import json
import os
import urllib.request

from utils.logger import logger

HOOK_URL = os.environ['HOOK_URL']

def send_message(log_file_names: str, instance_ids: str, s3_link: str, bucket: str, prefix :str):   
    message = ""

    message=f"""
:warning: *[ALERT-WARNING-S3]*
*- DATETIME*: {datetime.datetime.now(dateutil.tz.gettz('Asia/Seoul'))}
*- S3*: <{s3_link}|링크>
*- S3 PATH*: `s3://{bucket}/{prefix}`
*- S3 FILES*: {log_file_names}
*- ELB INSTANCES*: {instance_ids}
*- MESSAGE*: 누락된 로그가 있습니다
"""

    send_data = {
        "text": message,
    }
    send_text = json.dumps(send_data)
    request = urllib.request.Request(
        HOOK_URL,
        data=send_text.encode('utf-8'), 
    )
    response = urllib.request.urlopen(request)
    logger.info(f"Slack Response: {str(response)}")
