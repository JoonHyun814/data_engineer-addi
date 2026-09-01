import boto3
from utils.logger import logger

STATE_MACHINE_ARN = "arn:aws:states:ap-northeast-2:170217667865:stateMachine:ptbwa-postback-log-etl-hourly:prod"
step_function = boto3.client('stepfunctions')

def is_running_step_function(state_function_arn: str):

    excutions = step_function.list_executions(
        stateMachineArn=state_function_arn
    )

    logger.info(f"Step Function Execution: {str(excutions)}")
    logger.info(f"Step Function Recent Executions: {str(excutions['executions'][0])}")

    if excutions['executions'][0]['status'] in ['RUNNING', 'PENDING_REDRIVE']:
        return True
    else:
        return False