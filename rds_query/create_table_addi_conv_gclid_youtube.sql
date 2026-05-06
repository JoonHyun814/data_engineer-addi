CREATE TABLE `addi_conv_gclid_youtube` (
  `Date`       VARCHAR(10)   NOT NULL,
  `cmp_you_no` BIGINT        NULL,
  `CMP_name`   VARCHAR(255)  NULL,
  `gclid`      VARCHAR(255)  NULL,
  `created_at` DATETIME(3)   NULL,
  `year`       CHAR(4)       NOT NULL,
  `month`      CHAR(2)       NOT NULL,
  `day`        CHAR(2)       NOT NULL,
  INDEX `idx_day` (`year`, `month`, `day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
