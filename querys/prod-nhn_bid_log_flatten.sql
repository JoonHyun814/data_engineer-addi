-- CREATE TABLE "prod-ptbwa-dw"."nhn_bid_log_flatten"
-- WITH (
--     format = 'Parquet',
--     external_location = 's3://ptbwa-dw/prod/nhn_bid_log_flatten/',
--     partitioned_by = ARRAY['year', 'month', 'day', 'hour']
-- ) AS
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
    --site (현재 크롤링된 스키마엔 app 구조체가 없어 site만 포함)
    t.req.site.page AS site_page,
    t.req.site.id AS site_id,
    t.req.site.domain AS site_domain,
    t.req.site.name AS site_name,
    t.req.site.cat AS site_cat,
    t.req.site.publisher.id AS site_publisher_id,
    t.req.site.publisher.name AS site_publisher_name,
    t.req.site.publisher.domain AS site_publisher_domain,
    --device
    t.req.device.ua AS device_ua,
    t.req.device.ip AS device_ip,
    t.req.device.os AS device_os,
    t.req.device.osv AS device_osv,
    t.req.device.geo.country AS device_geo_country,
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
