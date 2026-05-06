CREATE TABLE `addi_conv_metric_youtube` (
  `Date`          VARCHAR(10)   NOT NULL,
  `campaign_no`   BIGINT        NULL,
  `campaign_name` VARCHAR(255)  NULL,
  `impressions`   BIGINT        NULL,
  `interactions`  BIGINT        NULL,
  `clicks`        BIGINT        NULL,
  `conversions`   DOUBLE        NULL,
  `created_at`    DATETIME(3)   NULL,
  `year`          CHAR(4)       NOT NULL,
  `month`         CHAR(2)       NOT NULL,
  `day`           CHAR(2)       NOT NULL,
  INDEX `idx_day` (`year`, `month`, `day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
