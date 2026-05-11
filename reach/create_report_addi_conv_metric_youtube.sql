CREATE TABLE "prod_addi_conv"."report_addi_conv_metric_youtube"
WITH (
    external_location = 's3://ptbwa-athena/prod_addi_conv/report_addi_conv_metric_youtube/',
    format = 'PARQUET',
    write_compression = 'SNAPPY'
) AS
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
WHERE metric.date BETWEEN '2026-01-01' AND '2026-05-09'
GROUP BY
    1, 2, 3, 4
ORDER BY
    metric.date,
    metric.campaign_no;
