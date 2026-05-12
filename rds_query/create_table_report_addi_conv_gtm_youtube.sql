CREATE TABLE `report_addi_conv_gtm_youtube` (
  `cmp_no`          BIGINT        NULL,
  `pid`             VARCHAR(100)  NULL,
  `cmp_you_no`      VARCHAR(100)  NULL,
  `ev`              VARCHAR(100)  NULL,
  `dt`              DATE          NULL,
  `daily_unique_ip` BIGINT        NULL,
  `year`            CHAR(4)       NOT NULL,
  `month`           CHAR(2)       NOT NULL,
  `day`             CHAR(2)       NOT NULL,
  INDEX `idx_day` (`year`, `month`, `day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
