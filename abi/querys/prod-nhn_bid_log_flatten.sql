-- CREATE TABLE "prod-ptbwa-dw"."nhn_bid_log_flatten"
-- WITH (
--     format = 'Parquet',
--     external_location = 's3://ptbwa-dw/prod/nhn_bid_log_flatten/',
--     partitioned_by = ARRAY['year', 'month', 'day', 'hour']
-- ) AS
-- NOTE: 2026-09-02에 querys/adhoc-nhn_bid_log_flatten_recreate.sql로 테이블을 재생성함
-- (ALTER TABLE ADD COLUMN이 이 엔진에서 파싱 에러로 실패해서 DROP+CTAS로 대체).
-- Athena INSERT INTO는 컬럼을 이름이 아니라 위치로 매칭하므로,
-- 아래 SELECT 컬럼 순서는 반드시 실제 테이블(재생성 시 CTAS) 순서와 동일해야 함.
-- 컬럼을 추가/변경할 때는 이 파일과 recreate 파일의 순서를 항상 같이 맞출 것.
INSERT INTO "prod-ptbwa-dw"."nhn_bid_log_flatten"
SELECT
    t.req.id AS req_id,
    t.req.at AS req_at,
    t.req.tmax AS req_tmax,
    t.req.cur AS currency_list,
    t.req.bcat AS req_bcat,
    t.req.badv AS req_badv,
    t.req.media_id AS media_id,
    t.created_at AS created_at,
    --imp
    TRY(t.req.imp[1].id) AS imp_id,
    TRY(t.req.imp[1].tagid) AS imp_tagid,
    TRY(t.req.imp[1].bidfloor) AS imp_bidfloor,
    TRY(t.req.imp[1].bidfloorcur) AS imp_bidfloorcur,
    TRY(t.req.imp[1].secure) AS imp_secure,
    TRY(t.req.imp[1].deal_type) AS imp_deal_type,
    TRY(t.req.imp[1].ad_type) AS imp_ad_type,
    TRY(t.req.imp[1].banner.w) AS imp_banner_w,
    TRY(t.req.imp[1].banner.h) AS imp_banner_h,
    TRY(t.req.imp[1].banner.pos) AS imp_banner_pos,
    TRY(t.req.imp[1].displaymanager) AS imp_displaymanager,
    TRY(t.req.imp[1].instl) AS imp_instl,
    TRY(t.req.imp[1].metric[1].type) AS imp_metric_type,
    TRY(t.req.imp[1].metric[1].value) AS imp_metric_value,
    TRY(t.req.imp[1].metric[1].vendor) AS imp_metric_vendor,
    TRY(t.req.imp[1].native.request) AS imp_native_request,
    TRY(t.req.imp[1].native.ver) AS imp_native_ver,
    TRY(t.req.imp[1].native.api) AS imp_native_api,
    TRY(t.req.imp[1].native.battr) AS imp_native_battr,
    --site
    t.req.site.page AS site_page,
    t.req.site.id AS site_id,
    t.req.site.domain AS site_domain,
    t.req.site.name AS site_name,
    t.req.site.cat AS site_cat,
    t.req.site.mobile AS site_mobile,
    t.req.site.publisher.id AS site_publisher_id,
    t.req.site.publisher.name AS site_publisher_name,
    t.req.site.publisher.domain AS site_publisher_domain,
    --device
    t.req.device.ua AS device_ua,
    t.req.device.ip AS device_ip,
    t.req.device.os AS device_os,
    t.req.device.osv AS device_osv,
    t.req.device.ifa AS device_ifa,
    t.req.device.geo.country AS device_geo_country,
    t.req.device.geo.lat AS device_geo_lat,
    t.req.device.geo.lon AS device_geo_lon,
    t.req.device.geo.city AS device_geo_city,
    t.req.device.geo.type AS device_geo_type,
    t.req.device.geo.zip AS device_geo_zip,
    t.req.device.geo.region AS device_geo_region,
    t.req.device.geo.utcoffset AS device_geo_utcoffset,
    t.req.device.geo.accuracy AS device_geo_accuracy,
    t.req.device.lmt AS device_lmt,
    t.req.device.carrier AS device_carrier,
    t.req.device.make AS device_make,
    t.req.device.model AS device_model,
    t.req.device.devicetype AS device_devicetype,
    t.req.device.language AS device_language,
    t.req.device.connectiontype AS device_connectiontype,
    t.req.device.pxratio AS device_pxratio,
    t.req.device.w AS device_w,
    t.req.device.h AS device_h,
    TRY(t.req.device.sua.browsers[1].brand) AS device_sua_browsers_brand,
    TRY(t.req.device.sua.browsers[1].version) AS device_sua_browsers_version,
    t.req.device.sua.platform.brand AS device_sua_platform_brand,
    t.req.device.sua.platform.version AS device_sua_platform_version,
    t.req.device.sua.mobile AS device_sua_mobile,
    t.req.device.sua.source AS device_sua_source,
    t.req.device.sua.architecture AS device_sua_architecture,
    t.req.device.sua.bitness AS device_sua_bitness,
    t.req.device.sua.model AS device_sua_model,
    --app
    t.req.app.name AS app_name,
    t.req.app.ver AS app_ver,
    t.req.app.bundle AS app_bundle,
    t.req.app.storeurl AS app_storeurl,
    t.req.app.id AS app_id,
    t.req.app.cat AS app_cat,
    t.req.app.publisher.id AS app_publisher_id,
    t.req.app.publisher.name AS app_publisher_name,
    t.req.app.publisher.domain AS app_publisher_domain,
    t.req.app.content.url AS app_content_url,
    t.req.app.content.language AS app_content_language,
    t.req.app.content.userrating AS app_content_userrating,
    t.req.app.content.genre AS app_content_genre,
    t.req.app.content.producer AS app_content_producer,
    --user
    t.req.user.id AS user_id,
    --res
    t.res.id AS res_id,
    t.fail_code AS fail_code,
    s.seatbid_row.impid AS impid,
    s.seatbid_row.price AS price,
    s.seatbid_row.crid AS crid,
    s.seatbid_row.cmp_no AS cmp_no,
    s.seatbid_row.ag_no AS ag_no,
    s.seatbid_row.crtv_no AS crtv_no,
    t.year AS year,
    t.month AS month,
    t.day AS day,
    t.hour
FROM
    "propfit"."nhn_bid_log" as t
LEFT JOIN UNNEST(t.res.seatbid) AS s (seatbid_row) ON TRUE
WHERE
    t.year = '{input_year}'
    AND t.month='{input_month}'
    AND t.day='{input_day}'
    AND t.hour='{input_hour}'
