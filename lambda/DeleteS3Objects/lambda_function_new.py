from delete_object import DeleteObject
from utils.logger import logger

def lambda_handler(event, context):
    try:
        
        date = event.get('date')
        bucket = event["bucket"]    
        dirs = event["dirs"] if event["dirs"][-1] != '/' else event["dirs"][:-1]
        athena_table_name = dirs.split('/')[-1]
        if 'media_cds' in list(event.keys()):
            media_cds = event["media_cds"] 
            logger.info(f"Media Codes: {str(media_cds)}")
        else:
            media_cds = None

        logger.info(f"Bucket: {bucket}")
        logger.info(f"Dirs: {dirs}")
        logger.info(f"Athena Table Name: {athena_table_name}")
        

        assert date, Exception("Missing required 'date' field in Step Functions input.")

        if media_cds is None:
            delete_obejct = DeleteObject(
                bucket=bucket,
                dirs=dirs, 
                date=date,
                athena_table_name=athena_table_name             
            )
            delete_obejct.proc_all()
        else:
            for media_cd in media_cds.split(','):
                delete_obejct = DeleteObject(
                    bucket=bucket,
                    dirs=dirs, 
                    date=date,
                    athena_table_name=athena_table_name,
                    media_cd=media_cd             
                )
                delete_obejct.proc_all()

        # if not date_str:
        #     return {
        #         'statusCode': 400,
        #         'body': { 'error': "Missing required 'date' field in Step Functions input." }
        #     }
        
        


        
        # try:
        #     input_date = datetime.strptime(date_str, "%Y-%m-%d")
        #     logger.info(f"Date: {input_date}")
            
        #     input_year = input_date.year
        #     input_month = "{:02d}".format(input_date.month)
        #     input_day = "{:02d}".format(input_date.day)

        #     if athena_table_name in ['addi_report_basic_customer_daily', 'addi_report_channel_customer_daily', 'addi_report_area_customer_daily']:
        #         key = f"{dirs}/date={input_year}-{input_month}-{input_day}"
        #     else:
        #         key = f"{dirs}/year={input_year}/month={input_month}/day={input_day}"
        #     # key="tt-step_function_test/year=2025/month=05/day=01/"
        # except:
        #     input_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

        #     logger.info(f"Date: {input_date}")

        #     input_year = input_date.year
        #     input_month = "{:02d}".format(input_date.month)
        #     input_day = "{:02d}".format(input_date.day)
        #     input_hour = "{:02d}".format(input_date.hour)

        #     if athena_table_name in ['addi_report_basic_customer_hour']:
        #         key = f"{dirs}/date={input_year}-{input_month}-{input_day}/hh={input_hour}"
        #     else:
        #         key = f"{dirs}/year={input_year}/month={input_month}/day={input_day}/hour={input_hour}"
        #     # key="tt-step_function_test/year=2025/month=05/day=01/"

        #     pass

        # response = s3.list_objects(
        #     Bucket=bucket,
        #     Prefix=key
        # )

        # logger.info(f"S3 List Objects: {str(response)}")

        # objects_key = list()
        # if 'Contents' in response:
        #     for content in response['Contents']:
        #         object_key = content['Key']
        #         logger.info(f"Object Key: {object_key}")
        #         objects_key.append(object_key)

        # for object_key in objects_key:
        #     s3.delete_object(
        #         Bucket=bucket,
        #         Key=object_key
        #     )
        #     logger.info(f"삭제 완료! :{object_key}")

        # return True
    except Exception as e:
        logger.error(e)
        raise e
    # logger.info(str(response))
