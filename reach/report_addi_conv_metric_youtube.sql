INSERT INTO "prod_addi_conv"."report_addi_conv_metric_youtube"
WITH info AS (
    SELECT DISTINCT
        cmp_no,
        cmp_you_no
    FROM "prod_addi_conv"."addi_conv_info"
),
aggregated AS (
    SELECT
        info.cmp_no,
        metric.campaign_no,
        metric.campaign_name,
        metric.date,
        SUM(metric.impressions) AS impressions,
        SUM(metric.trueviews) AS trueviews,
        SUM(metric.clicks) AS clicks,
        SUM(metric.conversions) AS conversions
    FROM "prod_addi_conv"."addi_conv_metric_youtube" metric
    LEFT JOIN info
        ON CAST(info.cmp_you_no AS BIGINT) = metric.campaign_no
    WHERE metric.date = '{date}'
    GROUP BY
        info.cmp_no,
        metric.campaign_no,
        metric.campaign_name,
        metric.date
)
SELECT
    cmp_no,
    campaign_no,
    campaign_name,
    date,
    impressions,
    trueviews,
    clicks,
    conversions,
    SUBSTR(date, 1, 4) AS year,
    SUBSTR(date, 6, 2) AS month,
    SUBSTR(date, 9, 2) AS day
FROM aggregated
ORDER BY date, campaign_no;
