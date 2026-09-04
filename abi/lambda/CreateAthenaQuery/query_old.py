import calendar
from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils.logger import logger
# TABLE = "\"tt-propfit\".\"step_function_test\""
 
def get_query(query_type: str, input_year: str='', input_month: str='', input_day: str='', input_hour: str='') -> str:
    exchange_date = datetime.strptime(f"{input_year}-{input_month}-{input_day}", "%Y-%m-%d")-relativedelta(months=1)
    exchange_year = exchange_date.year
    exchange_month = "{:02d}".format(exchange_date.month)
    exchange_last_day = calendar.monthrange(int(exchange_year), int(exchange_month))[1]

    if query_type.startswith("propfit_general_agg_"):
        logger.info(f"Exchange Date Range: {exchange_year}-{exchange_month}-01 ~ {exchange_year}-{exchange_month}-{exchange_last_day}")


    queries = {
        "ptbwa_apm_bid_flatten_insert":
f"""
INSERT INTO `prod-ptbwa-dw`.`apm_bid_log_flatten`
SELECT
    -- req
    t.req.req_id,
    t.req.at AS req_at,
    t.req.media_id,
    t.req.app_id,
    t.req.app_name,
    t.req.app_bundle,
    t.req.app_cate,
    t.req.site_id,
    t.req.site_name,
    t.req.site_domain,
    t.req.site_cate,
    t.req.publisher_id,
    t.req.publisher_name,
    t.req.publisher_domain,
    t.req.publisher_cate,
    t.req.ifa,
    t.req.language,
    t.req.os,
    t.req.ip,
    t.req.devicetype,
    t.req.content_id,
    t.req.content_title,
    t.req.content_genre,
    t.req.contentrating,
    t.req.country,
    t.req.zipcode,
    -- imp
    TRY(t.req.imp[1].id) AS imp_id,
    TRY(t.req.imp[1].tagid) AS imp_tagid,
    TRY(t.req.imp[1].bidfloorcur) AS imp_bidfloorcur,
    TRY(t.req.imp[1].bidfloor) AS imp_bidfloor,
    TRY(t.req.imp[1].deals) AS imp_deals,
    TRY(t.req.imp[1].deal_type) AS imp_deal_type,
    TRY(t.req.imp[1].mimes) AS imp_mimes,
    TRY(t.req.imp[1].minduration) AS imp_minduration,
    TRY(t.req.imp[1].maxduration) AS imp_maxduration,
    TRY(t.req.imp[1].w) AS imp_w,
    TRY(t.req.imp[1].h) AS imp_h,
    TRY(t.req.imp[1].ad_type) AS imp_ad_type,
    -- res
    t.res.id AS res_id,
    -- seatbid
    s.seatbid_row.price AS res_price,
    s.seatbid_row.deal_id AS res_deal_id,
    s.seatbid_row.bid_crtv_no AS res_bid_crtv_no,
    s.seatbid_row.bid_cmp_no AS res_bid_cmp_no,
    s.seatbid_row.bid_ag_no AS res_bid_ag_no,
    -- metadata
    from_iso8601_timestamp(t.created_at) AS created_at,
    t.year,
    t.month,
    t.day,
    t.hour
FROM
    "propfit"."bid_log" t
    LEFT JOIN UNNEST(filter(t.res.seatbid, sb -> sb.imp_id = TRY(t.req.imp[1].id))) AS s (seatbid_row) ON TRUE
WHERE
    t.year = \'{input_year}\'
    AND t.month=\'{input_month}\'
    AND t.day=\'{input_day}\'
    AND t.hour=\'{input_hour}\'
""",
        "ptbwa_abi_bid_flatten_insert":
f"""
INSERT INTO \"prod-ptbwa-dw\".\"abi_bid_log_flatten\"
SELECT
    t.req.id AS req_id,
    t.req.at AS req_at,
    t.req.tmax AS req_tmax,
    t.req.cur AS currency_list,
    t.req.media_id AS media_id,
    t.req.user.id AS req_user_id,
    t.created_at AS created_at,
    --imp
    TRY(t.req.imp[1].id) AS imp_id,
    TRY(t.req.imp[1].banner.w) AS imp_banner_w,
    TRY(t.req.imp[1].banner.h) AS imp_banner_h,
    TRY(t.req.imp[1].banner.pos) AS imp_banner_pos,
    TRY(t.req.imp[1].banner.format) AS imp_banner_format, 

    TRY(t.req.imp[1].video.mimes) AS imp_video_mimes,
    TRY(t.req.imp[1].video.linearity) AS imp_video_linearity,
    TRY(t.req.imp[1].video.minduration) AS imp_video_minduration,
    TRY(t.req.imp[1].video.maxduration) AS imp_video_maxduration,
    TRY(t.req.imp[1].video.w) AS imp_video_w,
    TRY(t.req.imp[1].video.h) AS imp_video_h,
    TRY(t.req.imp[1].video.startdelay) AS imp_video_startdelay,
    TRY(t.req.imp[1].video.pos) AS imp_video_pos,
    TRY(t.req.imp[1].video.api) AS imp_video_api,
    TRY(t.req.imp[1].video.companionad) AS imp_video_companionad,
    TRY(t.req.imp[1].native) AS imp_native,
    TRY(t.req.imp[1].displaymanager) AS imp_displaymanager,
    TRY(t.req.imp[1].instl) AS imp_instl,
    TRY(t.req.imp[1].tagid) AS imp_tagid,
    TRY(t.req.imp[1].bidfloor) AS imp_bidfloor,
    TRY(t.req.imp[1].bidfloorcur) AS imp_bidfloorcur,
    CASE
        WHEN TRY(t.req.imp[1].deal_type) = 'pmp' THEN TRY(t.req.imp[1].deals)
        ELSE CAST(NULL AS ARRAY(ROW(id VARCHAR, bidfloorcur VARCHAR, bidfloor DOUBLE, at INTEGER)))
    END AS imp_deals_array,
    TRY(t.req.imp[1].ad_type) AS imp_ad_type,
    TRY(t.req.imp[1].secure) AS imp_secure,
    TRY(t.req.imp[1].exp) AS exp,
    TRY(t.req.imp[1].ext.billing_id) AS ext_billing_id, 
    TRY(FILTER(t.req.imp[1].metric, m -> m.type = 'click_through_rate')[1].value) AS click_through_rate_value,
    TRY(FILTER(t.req.imp[1].metric, m -> m.type = 'viewability')[1].value) AS viewability_value,
    TRY(FILTER(t.req.imp[1].metric, m -> m.type = 'session_depth')[1].value) AS session_depth_value,
    TRY(FILTER(t.req.imp[1].metric, m -> m.type = 'click_through_rate')[1].vendor) AS click_through_rate_vendor,
    TRY(FILTER(t.req.imp[1].metric, m -> m.type = 'viewability')[1].vendor) AS viewability_vendor,
    TRY(FILTER(t.req.imp[1].metric, m -> m.type = 'session_depth')[1].vendor) AS session_depth_vendor,
    --app
    t.req.app.bundle AS app_bundle,
    t.req.app.name AS app_name,
    t.req.app.ver AS app_ver,
    t.req.app.storeurl AS app_storeurl,
    t.req.app.publisher.id AS app_publisher_id,
    t.req.app.content.data AS app_content_data, --ctv channel id 신규    
    t.req.app.content.url AS app_content_url,
    t.req.app.content.producer AS app_content_producer,
    t.req.app.content.producer.domain AS app_content_domain,
    t.req.app.content.language AS app_content_language,
    t.req.app.content.livestream AS app_content_livestream,
    t.req.app.content.userrating AS app_content_userrating,
    t.req.app.content.genre AS app_content_genre,
    --site
    t.req.site.page AS site_page,
    t.req.site.publisher.id AS site_publisher_id,
    t.req.site.content.genre AS site_content_genre,
    t.req.site.content.contentrating AS site_content_contentrating,
    t.req.site.content.livestream AS site_content_livestream,
    t.req.site.content.producer AS site_content_producer,
    t.req.site.content.language AS site_content_language,
    t.req.site.mobile AS site_mobile,
    --device
    t.req.device.ua AS device_ua,
    t.req.device.ip AS device_ip,
    t.req.device.geo.lat AS device_geo_lat,
    t.req.device.geo.lon AS device_geo_lon,
    t.req.device.geo.city AS device_geocity,
    t.req.device.geo.region AS device_geo_region,
    t.req.device.geo.country AS device_geo_country,
    t.req.device.geo.utcoffset AS device_utcoffset,
    t.req.device.geo.accuracy AS device_geo_accuracy,
    t.req.device.geo.zip AS device_geo_zip,
    t.req.device.carrier AS device_carrier,
    t.req.device.make AS device_make,
    t.req.device.model AS device_model,
    t.req.device.os AS device_os,
    t.req.device.osv AS device_osv,
    t.req.device.devicetype AS device_devicetype,
    t.req.device.connectiontype AS device_connectiontype,
    t.req.device.ifa AS device_ifa,
    t.req.device.w AS device_w,
    t.req.device.h AS device_h,
    t.req.device.pxratio AS device_pxratio,
    t.req.device.lmt AS device_lmt,
    TRY(t.req.device.sua.browsers[1].brand) AS device_sua_browsers_brand,
    TRY(t.req.device.sua.browsers[1].version) AS device_sua_browsers_version,
    t.req.device.sua.platform.brand AS device_sua_platform_brand,
    t.req.device.sua.platform.version AS device_sua_platform_version,
    t.req.device.sua.mobile AS device_sua_mobile,
    t.req.device.sua.bitness AS device_sua_bitness,
    t.req.device.sua.model AS device_sua_model,
    t.req.device.sua.architecture AS device_sua_architecture,
    
    TRY(t.req.ext.bid_feedback) AS req_ext_bid_feedback,
    TRY(t.req.ext.google_query_id) AS req_ext_google_query_id,
    TRY(t.req.ext.fcap_scope) AS req_ext_fcap_scope,
    TRY(t.req.ext.privacy_treatments.allow_user_data_collection) AS req_ext_allow_user_data_collection,
    
    --res
    s.seatbid_row.impid AS impid,
    s.seatbid_row.price AS price,
    s.seatbid_row.crtv_no AS crtv_no,
    s.seatbid_row.crid AS crid,
    s.seatbid_row.cmp_no AS cmp_no,
    s.seatbid_row.ag_no AS ag_no,
    s.seatbid_row.deal_id AS deal_id,
    t.year AS year,
    t.month AS month,
    t.day AS day,
    t.hour
FROM
    \"propfit\".\"ab_bid_log\" t,
    UNNEST(t.res.seatbid) AS s (seatbid_row)
WHERE
    t.year = \'{input_year}\'
    AND t.month=\'{input_month}\'
    AND t.day=\'{input_day}\'
    AND t.hour=\'{input_hour}\'
    AND t.res.id IS NOT NULL
""",

    "propfit_general_agg_hourly": 
f"""
INSERT INTO "dev-propfit-summary"."report_summary_hour"
with abi_price as (
    select 
        req_id,
        element_at(array_sort(array_agg(price)), -1) as price
    from 
        "propfit"."ab_postback_log" as postback

    left join
        "propfit-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
    group by 
        1
), abi_raw as (
    select 
        concat(postback.year, '-', postback.month, '-', postback.day, ' ', postback.hour, ':00:00') as DATETIME,
        postback.media_id as MEDIACD,
        cast(postback.cmp_no as int) as CMPNO,
        cast(postback.ag_no as int) as AGNO,
        cast(postback.creative_no as int) as CREATIVENO,
        COALESCE (
            (
                SELECT 
                    CAST(exchangerate AS DOUBLE)
                FROM 
                    "propfit-metadata"."exchangerate"
                WHERE
                    date_parse(cast(regd AS varchar), '%Y%m%d')  between date_parse('{exchange_year}-{exchange_month}-01', '%Y-%m-%d') and date_parse('{exchange_year}-{exchange_month}-{exchange_last_day}', '%Y-%m-%d')
                ORDER BY 
                    regd DESC 
                LIMIT 1
            ),
        0) as EXCHANGEWON,
        postback.req_id,
        postback.log_type,
        postback.is_cpvc,
        cast(abi_price.price as double) as price,
        year,
        month,
        day,
        hour
    from 
        "propfit"."ab_postback_log" as postback
    left join
        "propfit-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    left join 
        abi_price
    on
        abi_price.req_id=postback.req_id
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
), abi_report as (
    select 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO, 
        EXCHANGEWON,
        MEDIACD,
        count(distinct case when log_type='i' then req_id else null end) as IMPS,
        count(case when log_type='c' then req_id else null end) as CLICKS,
        sum(case when log_type='i' then CAST(price AS DOUBLE) else null end) as PAYMENT,
        count(distinct case when log_type!='e_i' and is_cpvc='1' then req_id else null end) as PAYMENTCNT,
        count(distinct case when log_type='v_firstQ' then req_id else null end) as Q1,
        count(distinct case when log_type='v_mid' then req_id else null end) as Q2,
        count(distinct case when log_type='v_thirdQ' then req_id else null end) as Q3,
        count(distinct case when log_type='v_complete' then req_id else null end) as Q4,
        count(case when log_type='e_i' then req_id else null end) as ERRORIMPS,
        sum(case when log_type='e_i' then CAST(price AS DOUBLE) else 0 end) as ERRORPAYMENT,
        year,
        month,
        day,
        hour
    from 
        abi_raw
    GROUP BY 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO, 
        EXCHANGEWON,
        MEDIACD,
        year,
        month,
        day,
        hour
), apm_raw as (
    select 
        distinct
            concat(postback.year, '-', postback.month, '-', postback.day, ' ', postback.hour, ':00:00') as DATETIME,
            req_id,
            cast(cmp_no as int) as CMPNO,
            cast(ag_no as int) as AGNO,
            cast(creative_no as int) as CREATIVENO,
            media_id as MEDIACD,
            COALESCE (
                (
                    SELECT 
                        CAST(exchangerate AS DOUBLE)
                    FROM 
                        "propfit-metadata"."exchangerate"
                    WHERE
                        date_parse(cast(regd AS varchar), '%Y%m%d')  between date_parse('{exchange_year}-{exchange_month}-01', '%Y-%m-%d') and date_parse('{exchange_year}-{exchange_month}-{exchange_last_day}', '%Y-%m-%d')
                    ORDER BY 
                        regd DESC 
                    LIMIT 1
                ),
            0) as EXCHANGEWON,
            log_type,
            is_cpvc,
            price,
            year,
            month,
            day,
            hour
    from 
        "propfit"."postback_log" as postback
    left join
        "propfit-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    where
        postback.req_id is not null
        and year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
), apm_report as (
    select 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO,
        EXCHANGEWON,
        MEDIACD,
        sum(case when log_type='i' then 1 else 0 end) as IMPS,
        sum(case when log_type='c' then 1 else 0 end) as CLICKS,
        sum(case when is_cpvc='1' then cast(price as double) else 0 end) as PAYMENT,
        sum(case when log_type!='e_i' then cast(is_cpvc as double) else 0 end) as PAYMENTCNT,
        sum(case when log_type='v_firstQ' then 1 else 0 end) as Q1,
        sum(case when log_type='v_mid' then 1 else 0 end) as Q2,
        sum(case when log_type='v_thirdQ' then 1 else 0 end) as Q3,
        sum(case when log_type='v_complete' then 1 else 0 end) as Q4,
        0 AS ERRORIMPS,
        0 AS ERRORPAYMENT,
        year,
        month,
        day,
        hour
    from 
        apm_raw
    GROUP BY 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO,
        EXCHANGEWON,
        MEDIACD,
        year,
        month,
        day,
        hour
)
SELECT 
    *
FROM
    abi_report
UNION ALL
SELECT 
    *
FROM
    apm_report
"""
    }

    return queries[query_type]