from utils.aws import s3
from utils.logger import logger
from datetime import datetime

class DeleteObject:
    def __init__(self, bucket: str, dirs: str, date: str, athena_table_name: str, media_cd: str=None):
        self.key = dirs
        self.bucket = bucket
        self.date = date
        self.athena_table_name = athena_table_name        
        self.media_cd = media_cd

    def proc_all(self):
        try:
            self.add_date_path()
            if self.media_cd is not None:
                self.add_media_cd_path()
            self.delete()
        except Exception as e:
            logger.error(f"[FAIL-PROC-ALL]{e}")
            raise e


    def add_date_path(self):
        logger.info("================== 날짜 경로 추가 ==================")

        try:
            converted_date = datetime.strptime(self.date, "%Y-%m-%d")
            logger.info(f"Date: {converted_date}")
            
            year = converted_date.year
            month = "{:02d}".format(converted_date.month)
            day = "{:02d}".format(converted_date.day)

            if self.athena_table_name in ['addi_report_basic_customer_daily', 'addi_report_channel_customer_daily', 'addi_report_area_customer_daily', 'addi_report_basic_customer_tax_daily']:
                self.key += f"/date={year}-{month}-{day}"
            else:
                self.key += f"/year={year}/month={month}/day={day}"
            # key="tt-step_function_test/year=2025/month=05/day=01/"
        except:
            converted_date = datetime.strptime(self.date, "%Y-%m-%d %H:%M:%S")

            logger.info(f"Date: {converted_date}")

            year = converted_date.year
            month = "{:02d}".format(converted_date.month)
            day = "{:02d}".format(converted_date.day)
            hour = "{:02d}".format(converted_date.hour)

            print(self.athena_table_name)
            if self.athena_table_name in ['addi_report_basic_customer_hour']:
                self.key += f"/date={year}-{month}-{day}/hh={hour}"
            else:
                self.key += f"/year={year}/month={month}/day={day}/hour={hour}"
            # key="tt-step_function_test/year=2025/month=05/day=01/"

            pass

        logger.info(f"Key: {self.key}")

    def add_media_cd_path(self):
        try:
            logger.info("================== 미디어 코드 경로 추가 ==================")
            if self.athena_table_name in ['addi_report_basic_customer_hour', 'addi_report_basic_customer_daily']:
                self.key += f"/media_cd={self.media_cd}"
            elif self.athena_table_name in ['addi_report_summary_hour', 'addi_report_summary_daily']:
                self.key += f"/mediacd={self.media_cd}"
            else:
                raise Exception(f"미디어 코드 경로 조건 식에 없는 테이블입니다. Table Name: {self.athena_table_name}")
            logger.info(f"Path: {self.key}")
        except Exception as e:
            logger.error(f"[FAIL-ADD-MEDIA-CD-PATH]{e}")
            raise e

    def delete(self):
        try:
            response = s3.list_objects(
                Bucket=self.bucket,
                Prefix=self.key
            )

            logger.info(f"S3 List Objects: {str(response)}")

            objects_key = list()
            if 'Contents' in response:
                for content in response['Contents']:
                    object_key = content['Key']
                    # logger.info(f"Object Key: {object_key}")
                    objects_key.append(object_key)

            logger.info(f"Objects Key: {str(objects_key)}")

            for object_key in objects_key:
                s3.delete_object(
                    Bucket=self.bucket,
                    Key=object_key
                )
                logger.info(f"삭제 완료! :{object_key}")

            # return True
        except Exception as e:
            logger.error(f"[FAIL-DELETE]{e}")
            raise e
