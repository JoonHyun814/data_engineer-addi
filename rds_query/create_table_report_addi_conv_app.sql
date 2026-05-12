CREATE TABLE `report_addi_conv_app` (
  `tracker`         VARCHAR(100)  NULL,
  `cmp`             VARCHAR(100)  NULL,
  `event`           VARCHAR(100)  NULL,
  `dt`              VARCHAR(10)   NOT NULL,
  `daily_unique_ip` BIGINT        NULL,
  `revenue`         DOUBLE        NULL,
  `year`            CHAR(4)       NOT NULL,
  `month`           CHAR(2)       NOT NULL,
  `day`             CHAR(2)       NOT NULL,
  INDEX `idx_day` (`year`, `month`, `day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
