import json
import urllib.request
# from utils.db import *
from data import ExportData
from utils.aws import glue
from utils.logger import logger

def check_ip():
    data = urllib.request.urlopen("https://checkip.amazonaws.com") # 현재 Instance의 IP를 반환
    ip = data.read()
    logger.info(f"IP: {ip}")
    return ip

def lambda_handler(event, context):
    check_ip()
    
    logger.info(f"Event: {str(event)}")
    
    db_cluster_name = event['db_cluster_name']
    db_name = event['db_name']
    crawler_names = event['crawler_names']
    tables = event['tables']

    logger.info(f"DB Cluster Name: {db_cluster_name}")
    logger.info(f"DB Name: {db_name}")
    logger.info(f"Crawler Names: {crawler_names}")
    logger.info(f"Tables: {str(tables)}")


    export_data = ExportData(db_cluster_name=db_cluster_name, db_name=db_name)
    for table in tables:        
        export_data.proc_all(table_name=table)
    export_data.disconnect_db()

    for crawler_name in crawler_names:
        glue.start_crawler(Name=crawler_name)


    # TODO implement
    # return {
    #     'statusCode': 200,
    #     'body': json.dumps('Hello from Lambda!')
    # }
