import datetime
import calendar
from utils.logger import logger
from dateutil.relativedelta import relativedelta


# input_year=''
# input_month=''
# input_day=''
# input_hour=''

class Date:
    @staticmethod
    def set_date(date_str: str):    
        try:
            # global input_year
            # global input_month
            # global input_day
            # global input_hour

            try:
                parsed_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                input_year = parsed_date.strftime("%Y")
                input_month = parsed_date.strftime("%m")
                input_day = parsed_date.strftime("%d")
                input_hour = ''
                logger.info(f"Input Date: {input_year}-{input_month}-{input_day}")
            except:
                parsed_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                input_year = parsed_date.strftime("%Y")
                input_month = parsed_date.strftime("%m")
                input_day = parsed_date.strftime("%d")
                input_hour = parsed_date.strftime("%H")
                logger.info(f"Input Date: {input_year}-{input_month}-{input_day} {input_hour}:00:00")
                pass

            return {
                'year': input_year,
                'month': input_month,
                'day': input_day,
                'hour': input_hour,
            }
        except Exception as e:
            logger.error(f"[SET-DATE]: {e}")
            raise e

        
    @staticmethod
    def get_exchange_date(input_date: dict) -> dict:
        try:        
            exchange_date = datetime.datetime.strptime(f"{input_date['year']}-{input_date['month']}-{input_date['day']}", "%Y-%m-%d")-relativedelta(months=1)
            exchange_year = exchange_date.year
            exchange_month = "{:02d}".format(exchange_date.month)
            exchange_last_month_day = calendar.monthrange(int(exchange_year), int(exchange_month))[1]
            
            exchange_first_date = f"{exchange_year}-{exchange_month}-01"
            exchange_last_date = f"{exchange_year}-{exchange_month}-{exchange_last_month_day}"
            
            # if query.query_type.startswith("propfit_general_agg_"):
            logger.info(f"Exchange Date Range: {exchange_first_date} ~ {exchange_last_date}")

            # return exchange_first_day, exchange_last_day
            return {
                "first": exchange_first_date,
                "last": exchange_last_date,
            }
        except Exception as e:
            logger.error(f"[GET-EXCHANGE-DATE]: {e}")
            raise e

    @staticmethod
    def get_yesterday_date(input_date: dict) -> dict:
        try:
            yesterday_date = datetime.datetime.strptime(f"{input_date['year']}-{input_date['month']}-{input_date['day']}", "%Y-%m-%d")-datetime.timedelta(days=1)
            yesterday_year = str(yesterday_date.year)
            yesterday_month = "{:02d}".format(yesterday_date.month)
            yesterday_day = "{:02d}".format(yesterday_date.day)


            # if query.query_type.startswith("propfit_general_agg_"):
            logger.info(f"Yesterday: {yesterday_year}-{yesterday_month}-{yesterday_day}")

            return {
                'year': str(yesterday_year),
                'month': str(yesterday_month),
                'day': str(yesterday_day)
            }
        except Exception as e:
            logger.error(f"[GET-YESTERDAY-DATE]: {e}")
            raise e
    
    @staticmethod
    def get_a_week_ago_date(input_date: dict) -> dict:
        try:
            a_week_ago_date = datetime.datetime.strptime(f"{input_date['year']}-{input_date['month']}-{input_date['day']}", "%Y-%m-%d")-datetime.timedelta(days=6)
            a_week_ago_date_year = str(a_week_ago_date.year)
            a_week_ago_date_month = "{:02d}".format(a_week_ago_date.month)
            a_week_ago_date_day = "{:02d}".format(a_week_ago_date.day)


            # if query.query_type.startswith("propfit_general_agg_"):
            logger.info(f"A Week Ago: {a_week_ago_date_year}-{a_week_ago_date_month}-{a_week_ago_date_day}")

            return {
                'year': str(a_week_ago_date_year),
                'month': str(a_week_ago_date_month),
                'day': str(a_week_ago_date_day),
                'date': f"{a_week_ago_date_year}-{a_week_ago_date_month}-{a_week_ago_date_day}"
            }
        except Exception as e:
            logger.error(f"[GET-A-WEEK-AGO-DATE]: {e}")
            raise e