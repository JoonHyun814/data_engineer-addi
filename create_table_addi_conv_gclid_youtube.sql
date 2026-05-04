CREATE TABLE `addi_conv_gclid_youtube` (
  `gclid`         VARCHAR(255)  NULL,
  `ad_group_ad`   VARCHAR(255)  NULL,
  `resource_name` VARCHAR(255)  NULL,
  `campaign`      VARCHAR(255)  NULL,
  `ad_group_id`   BIGINT        NULL,
  `ad_group_name` VARCHAR(255)  NULL,
  `c_id`          BIGINT        NULL,
  `c_name`        VARCHAR(255)  NULL,
  `year`          CHAR(4)       NOT NULL,
  `month`         CHAR(2)       NOT NULL,
  `day`           CHAR(2)       NOT NULL,
  INDEX `idx_day` (`day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
