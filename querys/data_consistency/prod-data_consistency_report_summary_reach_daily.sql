SELECT
    count(*) as error_cnt
FROM
    "prod-ptbwa-da"."report_summary_reach_daily" 


where
    year='{input_year}' and month='{input_month}' and day = '{input_day}'
    and (uniquereach<0 or dailyfrequency<0 or reach1<0 or reach2<0 or reach3<0) 