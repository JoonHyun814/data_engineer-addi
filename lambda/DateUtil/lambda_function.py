from datetime import datetime, timezone, timedelta


def lambda_handler(event, context):
    # end_date 미지정 시 KST 오늘 날짜로 대체 (실행 시점 기준 날짜가 필요한 파이프라인용)
    end_date = event.get('end_date') or datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    days     = int(event.get('date_diff', 14))

    end_obj    = datetime.strptime(end_date, '%Y-%m-%d')
    start_date = (end_obj - timedelta(days=days)).strftime('%Y-%m-%d')

    return {
        'start_date': start_date,
        'end_date':   end_date
    }
