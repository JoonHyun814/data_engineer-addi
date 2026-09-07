from datetime import datetime, timezone, timedelta


def lambda_handler(event, context):
    # end_date 미지정 시 KST 오늘 날짜로 대체 (실행 시점 기준 날짜가 필요한 파이프라인용)
    end_date = event.get('end_date') or datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    end_obj  = datetime.strptime(end_date, '%Y-%m-%d')

    # start_date가 이미 주어진 경우(날짜 범위 지정) 그대로 쓰고, 아니면 date_diff로 역산
    if event.get('start_date'):
        start_date = event['start_date']
    else:
        days       = int(event.get('date_diff', 14))
        start_date = (end_obj - timedelta(days=days)).strftime('%Y-%m-%d')
    start_obj = datetime.strptime(start_date, '%Y-%m-%d')

    # date_list: Step Functions Map의 ItemsPath가 배열을 요구하는데, JSONata Pass state로 만들면
    # 원소 1개짜리 배열이 스칼라로 축약되는 문제가 있어 Lambda(Python list)에서 직접 생성한다.
    date_list = [
        (start_obj + timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range((end_obj - start_obj).days + 1)
    ]

    return {
        'start_date': start_date,
        'end_date':   end_date,
        'date_list':  date_list
    }
