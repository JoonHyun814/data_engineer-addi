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
        COALESCE(SUM(metric.impressions), 0) AS impressions,
        COALESCE(SUM(metric.trueviews), 0) AS trueviews,
        COALESCE(SUM(metric.clicks), 0) AS clicks,
        COALESCE(SUM(metric.conversions), 0) AS conversions
    FROM "prod_addi_conv"."addi_conv_metric_youtube" metric
    LEFT JOIN info
        ON CAST(info.cmp_you_no AS BIGINT) = metric.campaign_no
    WHERE metric.date BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY
        info.cmp_no,
        metric.campaign_no,
        metric.campaign_name,
        metric.date
)
SELECT
    COALESCE(cmp_no, 0) AS cmp_no,
    campaign_no,
    COALESCE(campaign_name, '') AS campaign_name,
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
