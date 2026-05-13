CREATE TABLE `report_addi_conv_metric_youtube` (
  `cmp_no`        BIGINT        NULL,
  `campaign_no`   BIGINT        NULL,
  `campaign_name` VARCHAR(255)  NULL,
  `date`          VARCHAR(10)   NOT NULL,
  `impressions`   BIGINT        NULL,
  `trueviews`     BIGINT        NULL,
  `clicks`        BIGINT        NULL,
  `conversions`   DOUBLE        NULL,
  `year`          CHAR(4)       NOT NULL,
  `month`         CHAR(2)       NOT NULL,
  `day`           CHAR(2)       NOT NULL,
  INDEX `idx_day` (`year`, `month`, `day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
