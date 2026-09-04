import json
import dateutil
from datetime import datetime, timedelta
from utils.aws import step_function, STATE_MACHINE_ARN, is_running_step_function
from utils.logger import logger

def lambda_handler(event, context):
    # TODO implement

    a_hour_ago_datetime = datetime.now(dateutil.tz.gettz('Asia/Seoul')) - timedelta(hours=1)
    a_hour_ago_created_time = {
        'year': str(a_hour_ago_datetime.year),
        'month': "{:02d}".format(a_hour_ago_datetime.month),
        'day': "{:02d}".format(a_hour_ago_datetime.day),
        'hour': "{:02d}".format(a_hour_ago_datetime.hour),
    }
    
    logger.info(f"A Hour Ago Datetime: {a_hour_ago_datetime}")    
    logger.info(f"Event: {str(event)}")
    logger.info(f"Context: {str(context)}")

    log_path = event['detail']['object']['key'].split('/')
    logger.info(f"Log Path: {log_path}")


    log_created_time = {
        'year': '',
        'month': '',
        'day': '',
        'hour': ''
    }
    for p in log_path:        
        if '=' in p and p.split('=')[0] in list(log_created_time.keys()):
            k, v = p.split("=")
            log_created_time[k]=v

    if log_created_time['year']==a_hour_ago_created_time['year']\
        and log_created_time['month']==a_hour_ago_created_time['month']\
        and log_created_time['day']==a_hour_ago_created_time['day']\
        and log_created_time['hour']==a_hour_ago_created_time['hour']:

        if is_running_step_function(state_function_arn=STATE_MACHINE_ARN):
            logger.info(f"이미 Step Function 실행 중!")
        else:
            step_function_input = {
                "date": f"{log_created_time['year']}-{log_created_time['month']}-{log_created_time['day']} {log_created_time['hour']}:00:00",
            }

            step_function_response = step_function.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                input=json.dumps(step_function_input)
            )

            logger.info(f"Step Fucntion 실행 완료!: {str(step_function_response)}")
    else:
        logger.info(f"1시간 전 시간과 로그 생성 시각이 다름")

