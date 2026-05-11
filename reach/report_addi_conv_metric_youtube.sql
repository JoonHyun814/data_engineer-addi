INSERT INTO "prod_addi_conv"."report_addi_conv_metric_youtube"
WITH info AS (
    SELECT DISTINCT
        cmp_no,
        cmp_you_no
    FROM "prod_addi_conv"."addi_conv_info"
)
SELECT
    metric.date,
    info.cmp_no,
    metric.campaign_no,
    metric.campaign_name,
    SUM(metric.impressions) AS impressions,
    SUM(metric.trueviews) AS trueviews,
    SUM(metric.clicks) AS clicks,
    SUM(metric.conversions) AS conversions
FROM "prod_addi_conv"."addi_conv_metric_youtube" metric
LEFT JOIN info
    ON CAST(info.cmp_you_no AS BIGINT) = metric.campaign_no
WHERE metric.date = DATE_FORMAT(DATE_ADD('day', -1, CURRENT_DATE), '%Y-%m-%d')
GROUP BY
    1, 2, 3, 4
ORDER BY
    metric.date,
    metric.campaign_no;