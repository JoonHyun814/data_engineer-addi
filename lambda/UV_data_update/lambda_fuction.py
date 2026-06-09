import os
import json
import boto3
import requests
import pymysql
from datetime import datetime, timedelta, timezone

def get_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

def lambda_handler(event, context):
    # 1. Secrets Manager 로드
    db1_secret = get_secret('database-1')
    db_addi_secret = get_secret('database_addi')
    api_secret = get_secret('weather_API')
    
    endpoint = api_secret['UV_API_ENDPOINT']
    service_key = api_secret['UV_API_KEY']
    
    # 2. 시간 계산 (3의 배수 시 적용)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    hour = (now_kst.hour // 3) * 3
    time_str = now_kst.strftime(f"%Y%m%d{hour:02d}")
    
    # 3. regions 조회
    regions = []
    conn1 = pymysql.connect(
        host=db1_secret['host'],
        user=db1_secret['username'],
        password=db1_secret['password'],
        db=db1_secret.get('dbname', 'ptbwa_propfit'),
        port=int(db1_secret.get('port', 3306)),
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with conn1.cursor() as cursor:
            cursor.execute("SELECT region_code, adm_code FROM regions WHERE adm_code IS NOT NULL")
            regions = cursor.fetchall()
    finally:
        conn1.close()
        
    # 4. API 호출 및 구간별 weather_code 필터링 매핑
    weather_data = []
    api_url = f"{endpoint}/getUVIdxV5"
    
    for region in regions:
        region_code = region['region_code']
        adm_code = region['adm_code']
        
        params = {
            "serviceKey": service_key,
            "areaNo": adm_code,
            "time": time_str,
            "dataType": "JSON"
        }
        
        try:
            res = requests.get(api_url, params=params, timeout=5)
            if res.status_code == 200:
                res_json = res.json()
                items = res_json.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                
                if items:
                    h0_value = items[0].get('h0')
                    if h0_value is not None and h0_value != "":
                        h0_int = int(h0_value)
                        if h0_int >= 11:
                            w_code = "B001_004_005"
                        elif h0_int >= 8:
                            w_code = "B001_004_004"
                        elif h0_int >= 6:
                            w_code = "B001_004_003"
                        elif h0_int >= 3:
                            w_code = "B001_004_002"
                        else:
                            w_code = "B001_004_001"
                            
                        weather_data.append((region_code, w_code))
        except Exception as e:
            print(f"Error fetching API for {region_code}: {e}")
            
    # 5. addi DB 기존 데이터 삭제 후 신규 데이터 적재 (Delete & Insert)
    if weather_data:
        conn_addi = pymysql.connect(
            host=db_addi_secret['host'],
            user=db_addi_secret['username'],
            password=db_addi_secret['password'],
            db=db_addi_secret.get('dbname', 'addi'),
            port=int(db_addi_secret.get('port', 3306))
        )
        try:
            with conn_addi.cursor() as cursor:
                # 5-1. 기존 날씨 데이터 전체 비우기
                cursor.execute("TRUNCATE TABLE area_weather_codes")
                
                # 5-2. 최신 API 결과 데이터 일괄 삽입
                insert_query = """
                    INSERT INTO area_weather_codes (region_code, weather_code, moddt)
                    VALUES (%s, %s, NOW());
                """
                cursor.executemany(insert_query, weather_data)
            conn_addi.commit()
        except Exception as e:
            conn_addi.rollback()
            print(f"Database operation failed: {e}")
            raise e
        finally:
            conn_addi.close()
            
    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully cleared old data and loaded {len(weather_data)} new regions.')
    }