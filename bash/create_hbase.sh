# hbase_create_tables.sh
# 执行方式：hbase shell hbase_create_tables.sh

# ---------- 订单行为日志表 ----------
create 'order_behavior',
  {NAME => 'info',   TTL => 'FOREVER', VERSIONS => 1, BLOCKSIZE => '65536'},
  {NAME => 'extra',  TTL => 'FOREVER', VERSIONS => 1, BLOCKSIZE => '65536'},
  SPLITS => [
    '00|', '01|', '02|', '03|', '04|', '05|', '06|', '07|',
    '08|', '09|', '10|', '11|', '12|', '13|', '14|', '15|'
  ]

# ---------- 评论正文表 ----------
create 'comment_content',
  {NAME => 'content', TTL => 'FOREVER', VERSIONS => 1, BLOCKSIZE => '65536'},
  {NAME => 'meta',    TTL => 'FOREVER', VERSIONS => 1, BLOCKSIZE => '65536'},
  SPLITS => [
    'comment:0', 'comment:1', 'comment:2', 'comment:3',
    'comment:4', 'comment:5', 'comment:6', 'comment:7',
    'comment:8', 'comment:9'
  ]