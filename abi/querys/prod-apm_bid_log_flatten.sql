INSERT INTO "prod-ptbwa-dw"."apm_bid_log_flatten"
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
    t.year = '{input_year}'
    AND t.month='{input_month}'
    AND t.day='{input_day}'
    AND t.hour='{input_hour}'