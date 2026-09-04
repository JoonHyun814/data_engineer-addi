CREATE EXTERNAL TABLE IF NOT EXISTS `propfit`.`nhn_bid_log` (
  `req` struct<
    id:string,
    at:int,
    tmax:int,
    cur:array<string>,
    bcat:array<string>,
    badv:array<string>,
    media_id:string,
    imp:array<struct<
      id:string,
      tagid:string,
      bidfloor:double,
      bidfloorcur:string,
      secure:int,
      deal_type:string,
      banner:struct<w:int,h:int,pos:int>,
      ad_type:string,
      displaymanager:string,
      instl:int,
      metric:array<struct<type:string,value:double,vendor:string> >,
      native:struct<request:string,ver:string,api:array<int>,battr:array<int> >
    > >,
    site:struct<
      page:string,
      id:string,
      domain:string,
      name:string,
      cat:array<string>,
      publisher:struct<id:string,name:string,domain:string>,
      mobile:int
    >,
    device:struct<
      ua:string,
      ip:string,
      os:string,
      osv:string,
      geo:struct<country:string,lat:double,lon:double,city:string,type:int,zip:string,region:string,utcoffset:int,accuracy:int>,
      lmt:int,
      carrier:string,
      make:string,
      model:string,
      devicetype:int,
      ifa:string,
      language:string,
      sua:struct<
        browsers:array<struct<brand:string,version:array<string> > >,
        platform:struct<brand:string,version:array<string> >,
        mobile:int,
        source:int,
        architecture:string,
        bitness:string,
        model:string
      >,
      connectiontype:int,
      pxratio:double,
      w:int,
      h:int
    >,
    user:struct<id:string>,
    app:struct<
      name:string,
      ver:string,
      bundle:string,
      storeurl:string,
      id:string,
      cat:array<string>,
      publisher:struct<id:string,name:string,domain:string>,
      content:struct<url:string,language:string,userrating:string,genre:string,producer:string>
    >
  >,
  `created_at` string,
  `res` struct<
    id:string,
    seatbid:array<struct<
      impid:string,
      price:string,
      crid:string,
      crtv_no:string,
      cmp_no:int,
      ag_no:int,
      deal_id:string,
      adm:string
    > >
  >,
  `fail_code` int
)
PARTITIONED BY (
  `year` string,
  `month` string,
  `day` string,
  `hour` string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://propfit-bid-logs/nhn/propfit_log/nhn_bid_log/'
TBLPROPERTIES ('has_encrypted_data'='false');
