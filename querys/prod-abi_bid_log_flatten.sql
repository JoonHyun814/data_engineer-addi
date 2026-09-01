-- CREATE TABLE "prod-ptbwa-dw"."abi_bid_log_flatten"
-- WITH (
--     format = 'Parquet',
--     external_location = 's3://ptbwa-dw/prod/abi_bid_log_flatten/',
--     partitioned_by = ARRAY['year', 'month', 'day', 'hour']
-- ) AS
INSERT INTO "prod-ptbwa-dw"."abi_bid_log_flatten"
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
    TRY(t.req .ext.google_query_id) AS req_ext_google_query_id,
    TRY(t.req.ext.fcap_scope) AS req_ext_fcap_scope,
    TRY(t.req.ext.privacy_treatments.allow_user_data_collection) AS req_ext_allow_user_data_collection,	
    
    --res
	res.id AS res_id,    
    s.seatbid_row.price AS price,
    s.seatbid_row.crtv_no AS crtv_no,
    s.seatbid_row.crid AS crid,
    s.seatbid_row.cmp_no AS cmp_no,
    s.seatbid_row.ag_no AS ag_no,
    s.seatbid_row.deal_id AS deal_id,
	s.seatbid_row.impid AS impid,
	
	TRY(t.req.bcat) as req_bcat,
	
    t.year AS year,
    t.month AS month,
    t.day AS day,
    t.hour
 FROM
     "propfit"."ab_bid_log"  as t
 LEFT JOIN UNNEST(t.res.seatbid) AS s (seatbid_row) ON TRUE
WHERE
    t.year = '{input_year}'
    AND t.month='{input_month}'
    AND t.day='{input_day}'
    AND t.hour='{input_hour}'
    -- AND t.res.id IS NOT NULL