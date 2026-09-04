from utils.logger import logger
# from utils.query_new import get_query
# from utils.date import set_date
from utils.date import Date
from query import Query
# import utils.date 
from datetime import datetime, timedelta
import json


# query.py 파일에서 get_query 함수를 임포트합니다.
# import query

def lambda_handler(event, context):
    query_type = event.get('query_type')
    date_str = event.get('date')
    dirs = event.get('dirs')

    if not date_str:
        utc_now = datetime.utcnow()
        kst_now = utc_now + timedelta(hours=9)
        yesterday = kst_now - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')
    # assert date_str, Exception("Missing required 'date' field in Step Functions input.")
    assert query_type, Exception("Missing required 'query_type' field in Step Functions input.")

    input_date = Date.set_date(date_str=date_str)
    # set_query_type(_type=query_type)

    try:
        query = Query(query_type=query_type, input_date=input_date, dirs=dirs)
        generated_sql_query = query.proc_all()
        # generated_sql_query = get_query(query_type=query_type, input_date=input_date, dirs=dirs)

        # step function 이 원하는 구조로 수정
        return {
            # 'query_type_requested_by_step_functions': step_function_query_type,
            'query_type_used_in_query_py': query_type,
            'input_year': input_date['year'],
            'input_month': input_date['month'],
            'input_day': input_date['day'],
            'input_hour': input_date['hour'],
            'generated_sql_query': generated_sql_query 
        }

    except Exception as e:
        logger.error(e)
        return {
            'error': f"Error generating query: {str(e)}"
        }
