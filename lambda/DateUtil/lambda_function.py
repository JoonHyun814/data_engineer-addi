from datetime import datetime, timedelta


def lambda_handler(event, context):
    end_date = event['end_date']
    days     = int(event.get('date_diff', 14))

    end_obj    = datetime.strptime(end_date, '%Y-%m-%d')
    start_date = (end_obj - timedelta(days=days)).strftime('%Y-%m-%d')

    return {
        'start_date': start_date,
        'end_date':   end_date
    }
