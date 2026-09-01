import utils.date 
import re

from utils.aws import s3
from utils.logger import logger
# from utils.date import set_date, get_exchange_date, get_yesterday_date, get_a_week_ago_date
from utils.date import Date
from datetime import datetime, timedelta

QUERY_BUCKET = "ptbwa-athena"
BASE_DIR = "query"
# BASE_DIR = "query/soomgo_query"
# query_type = ''

# def set_query_type(_type: str):
#     global query_type
#     query_type=_type
#     logger.info(f"Query type: {query_type}")


class Query:
    def __init__(self, query_type: str, input_date: dict, dirs: str):
        self.query_type = query_type
        self.input_date = input_date
        self.dirs = dirs

    def proc_all(self):
        try:
            target_file_path = self.download_query_from_s3()
            query = self.get_query_from_file(file_path=target_file_path)
            query = self.convert_query(query=query)
            return query
        except Exception as e:
            logger.error(f"[FAIL-PROC-ALL] {e}")
            raise e

    def download_query_from_s3(self):
        try:
            source_file_path = f"{BASE_DIR}/{self.dirs}/{self.query_type}.sql"
            target_file_path = f"/tmp/{self.query_type}.sql"

            logger.info(f"Bucket: {QUERY_BUCKET}")
            logger.info(f"Dirs: {BASE_DIR}/{self.dirs}")
            logger.info(f"Source File Path: {source_file_path}")
            logger.info(f"Target File Path: {target_file_path}")

            response = s3.download_file(QUERY_BUCKET, source_file_path, target_file_path)

            logger.info(f"S3 Download File Response: {response}")

            return target_file_path
            # query = get_query_from_file(file_path=target_file_path)
            # query = convert_query(query_type=query_type, query=query, input_date=input_date)
            # return query
        except Exception as e:
            logger.error(f"[FAIL-DOWNLOAD-QUERY-FROM-S3] {e}")
            raise e
        

    def get_query_from_file(self, file_path: str) -> str:
        try:
            f = open(file_path, "r") 
            lines = f.readlines()
            query = ' '.join(lines)
            f.close()

            logger.info(f"Query: {query}")

            return query
        except Exception as e:
            logger.error(f"[FAIL-GET-QUERY-FROM-FILE] {e}")
            raise e

    def convert_query(self, query: str) -> str:
        try:
            # if query_type.endswith("propfit_general_agg_"):
            if re.search(r"(dev|prod)-(addi_)?report_summary_(hour|daily)", self.query_type):
                exchange_date = Date.get_exchange_date(input_date=self.input_date)
                query = query.replace("{exchange_first_day}", exchange_date['first'])
                query = query.replace("{exchange_last_day}", exchange_date['last'])
            elif re.search(r"(dev|prod)-(addi_)?report_summary_channel_daily", self.query_type):
                input_yesterday = Date.get_yesterday_date(input_date=self.input_date)
                query = query.replace("{input_yesterday_year}", input_yesterday['year'])
                query = query.replace("{input_yesterday_month}", input_yesterday['month'])
                query = query.replace("{input_yesterday_day}", input_yesterday['day'])
            elif re.search(r"(dev|prod)-tg_ip_pairing_weekly", self.query_type):
                input_a_week_ago =  Date.get_a_week_ago_date(input_date=self.input_date)            
                query = query.replace("{input_input_a_week_ago_date}", input_a_week_ago['date'])

            query = query.replace("{input_year}", self.input_date['year'])
            query = query.replace("{input_month}", self.input_date['month'])
            query = query.replace("{input_day}", self.input_date['day'])
            query = query.replace("{input_date}", f'{self.input_date['year']}-{self.input_date['month']}-{self.input_date['day']}')

            # if re.search(r"_hour$", query_type):
            query = query.replace("{input_hour}", self.input_date['hour'])

            logger.info(f"Converted Query: {query}")

            return query
        except Exception as e:
            logger.error(f"[FAIL-CONVERT-QUERY] {e}")
            raise e



# def get_query_from_file(file_path: str) -> str:
#     try:
#         f = open(file_path, "r") 
#         lines = f.readlines()
#         query = ' '.join(lines)
#         f.close()

#         logger.info(f"Query: {query}")

#         return query
#     except Exception as e:
#         logger.error(f"[GET-QUERY-FROM-FILE] {e}")
#         raise e

# def convert_query(query_type: str, query: str, input_date: dict) -> str:
#     try:
#         # if query_type.endswith("propfit_general_agg_"):
#         if re.search(r"(dev|prod)-(addi_)?report_summary_(hour|daily)", query_type):
#             exchange_date = get_exchange_date(input_date=input_date)
#             query = query.replace("{exchange_first_day}", exchange_date['first'])
#             query = query.replace("{exchange_last_day}", exchange_date['last'])
#         elif re.search(r"(dev|prod)-(addi_)?report_summary_channel_daily", query_type):
#             input_yesterday = get_yesterday_date(input_date=input_date)
#             query = query.replace("{input_yesterday_year}", input_yesterday['year'])
#             query = query.replace("{input_yesterday_month}", input_yesterday['month'])
#             query = query.replace("{input_yesterday_day}", input_yesterday['day'])
#         elif re.search(r"(dev|prod)-tg_ip_pairing_weekly", query_type):
#             input_a_week_ago =  get_a_week_ago_date(input_date=input_date)            
#             query = query.replace("{input_input_a_week_ago_date}", input_a_week_ago['date'])

#         query = query.replace("{input_year}", input_date['year'])
#         query = query.replace("{input_month}", input_date['month'])
#         query = query.replace("{input_day}", input_date['day'])
#         query = query.replace("{input_date}", f'{input_date['year']}-{input_date['month']}-{input_date['day']}')

#         # if re.search(r"_hour$", query_type):
#         query = query.replace("{input_hour}", input_date['hour'])

#         logger.info(f"Converted Query: {query}")

#         return query
#     except Exception as e:
#         logger.error(f"[CONVERT-QUERY] {e}")
#         raise e


# def get_query(query_type: str, input_date: dict, get_query) -> str:
#     try:
#         # global query_type

#         source_file_path = f"{BASE_DIR}/{query_type}.sql"
#         target_file_path = f"/tmp/{query_type}.sql"

#         logger.info(f"Bucket: {QUERY_BUCKET}")
#         logger.info(f"Source File Path: {source_file_path}")
#         logger.info(f"Target File Path: {target_file_path}")

#         response = s3.download_file(QUERY_BUCKET, source_file_path, target_file_path)
        
#         # logger.info(f"S3 Download File Response: {response}")
#         query = get_query_from_file(file_path=target_file_path)
#         query = convert_query(query_type=query_type, query=query, input_date=input_date)
#         return query
#     except Exception as e:
#         logger.error(f"[GET-QUERY] {e}")
#         raise e