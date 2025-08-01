# mysql-backup

用于备份数据库、备份清理、备份恢复

- 支持保留备份数
- 支持全量备份
- 支持单数据库备份
- 支持单集合备份
- 支持忽略若干集合备份
- 支持选择备份恢复
- 支持加密备份

## Quick Start

支持三种方式使用

- 命令行
- docker
- helm chart

### 使用命令行

全量数据库备份和恢复

```shell
# 使用文件备份
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 BACKUP_PATH=./backup FILE_PREFIX=tmp python docker/backup.py
# 启用 s3 备份
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 BACKUP_PATH=./backup FILE_PREFIX=tmp S3_ENABLE=true S3_EP="https://minio-api.36node.com" S3_ACCESS_KEY="xxxx" S3_ACCESS_SECRET="xxxx" S3_BUCKET="test" S3_PREFIX="prefix" python docker/backup.py

# 使用文件恢复
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 BACKUP_PATH=./backup python docker/restore.py
# 使用 s3 恢复
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 RESTORE_FROM_S3=1 S3_EP="https://minio-api.36node.com" S3_ACCESS_KEY="xxxx" S3_ACCESS_SECRET="xxxx" S3_BUCKET="test" S3_PREFIX="prefix" python docker/restore.py
```

单个数据库备份和恢复

```shell
# 使用文件备份
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 BACKUP_PATH=./backup python docker/backup.py
# 启用 s3 备份
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 BACKUP_PATH=./backup FILE_PREFIX=tmp S3_ENABLE=1 S3_EP="https://minio-api.36node.com" S3_ACCESS_KEY="xxxx" S3_ACCESS_SECRET="xxxx" S3_BUCKET="test" S3_PREFIX="prefix" python docker/backup.py

# 使用文件恢复
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 BACKUP_PATH=./backup python docker/restore.py
# 使用 s3 恢复
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 RESTORE_FROM_S3=1 S3_EP="https://minio-api.36node.com" S3_ACCESS_KEY="xxxx" S3_ACCESS_SECRET="xxxx" S3_BUCKET="test" S3_PREFIX="prefix" python docker/restore.py
```

备份时忽略某些集合

```shell
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PWD=123456 MYSQL_EXCLUDE_TABLES=table1,table2 BACKUP_PATH=./backup python docker/backup.py
```

### 使用 docker

```shell
# backup
docker run -it --rm \
  -e MYSQL_HOST="127.0.0.1" \
  -e MYSQL_USER="root" \
  -e MYSQL_PWD="123456" \
  -v ./some-dir:/backup \
  36node/mysql-backup

# restore
docker run -it --rm \
  -e MYSQL_HOST="127.0.0.1" \
  -e MYSQL_USER="root" \
  -e MYSQL_PWD="123456" \
  -v ./some-dir:/backup \
  36node/mysql-backup \
  /app/restore.py
```

### 使用 helm-chart

```shell
# 确保你的 helm 客户端支持 oci
export HELM_EXPERIMENTAL_OCI=1

# 安装
helm -n mysql-backup-chart install mysql-backup oci://harbor.36node.com/common/mysql-backup:1.3.0 -f values.yaml
```

values 样例

```yaml
backup:
  enabled: true
  schedule: "0 0 * * *"
  hostPath: /opt
  nodeSelector:
    kubernetes.io/hostname: "worker-1"
  env:
    MYSQL_HOST: 127.0.0.1
    MYSQL_USER: root
    MYSQL_PWD: 123456
    FILE_PREFIX: xsjj
    BACKUP_SAVE_NUMS: 3
restore:
  enabled: true
  hostPath: /opt
  nodeSelector:
    kubernetes.io/hostname: "worker-1"
  env:
    MONGO_URI: "mysql://localhost:27017"
```

恢复

```shell
## 启动一个容器用于执行恢复脚本
kubectl -n mysql-backup scale deployment restore --replicas=1

## 查看这个容器启动的 pod
kubectl -n mysql-backup get pod

# 选择适当的备份进行恢复
kubectl -n mysql-backup exec -it restore-xxx-xxx -- python3 /app/restore.py
```

### 存储

支持 挂载磁盘 或 PVC，容器内的挂载路径默认为 `/backup`

- 本地磁盘，指定 nodeSelector 及 hostPath
- PVC，指定 existingClaim
- comming feature 支持 storage_class

### 关于 S3 endpoint 的说明

S3 支持使用虚拟域名作为 endpoint，即可以将 region 或者 bucket 放入域名中使用，不同的 S3 配置会略有不同，需进行测试。其他配置，可参考[boto3 文档](https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html)

- 36node 自建 minio，使用默认配置即可
- xxx.aliyuncs.com，需要设置 S3_EP_VIRTUAL 为 true

## 环境变量说明

### backup

- MYSQL_HOST: 必填，数据库地址，例如 localhost
- MYSQL_USER: 必填，数据库用户名
- MYSQL_PWD: 必填，数据库密码
- MYSQL_PORT: 选填，数据库端口，默认为 3306

- MYSQL_DBS: 选填，待备份数据库，支持多个，例如 test1,test2，若为空表示备份所有数据库
- MYSQL_TABLES: 选填，待备份表，支持多个，例如 test1,test2，仅在 MYSQL_DBS 有唯一值时生效，若为空表示备份该数据库下所有表
- MYSQL_EXCLUDE_TABLES: 选填，忽略的表名称，支持多个，例如 test1,test2，仅在 MYSQL_DBS 有唯一值且 MYSQL_TABLES 为空时生效
- MYSQL_OTHER_CMD: 选填，备份时的其他命令，支持多个，例如 --single-transaction,--skip-lock-tables
- FILE_PREFIX: 选填，备份文件前缀，例如 fcp
- BACKUP_SAVE_NUMS: 选填，备份保存数量，例如 3，默认保存 3 份
- BACKUP_PWD: 选填，加密密码，备份文件可用 zip 加密

- S3_ENABLE: 选填，是否启用 S3 存储备份，true 表示启用
- S3_EP: 选填，S3 url，例如 https://minio-api.36node.com
- S3_EP_VIRTUAL: 选填，是否启用虚拟 host url，true 表示启用
- S3_ACCESS_KEY: 选填，S3 access key
- S3_ACCESS_SECRET: 选填，S3 access secret
- S3_REGION: 选填，地区名
- S3_BUCKET: 选填，要存储的桶名
- S3_PREFIX: 选填，要存储的前缀

### restore

- S3_ENABLE: 选填，是否从 S3 中进行恢复，true 表示启用

同 backup 的变量

- MYSQL_HOST
- MYSQL_USER
- MYSQL_PWD
- MYSQL_PORT
- MYSQL_DBS
- MONGO_FILE_PREFIX
- BACKUP_PWD

- S3_EP
- S3_EP_VIRTUAL
- S3_ACCESS_KEY
- S3_ACCESS_SECRET
- S3_REGION
- S3_BUCKET
- S3_PREFIX

## Development

开发相关的涉及命令

```shell
# mysqldump
mysqldump --uri="mysql://localhost:27017" --db=test --collection=test --gzip --archive="/backup/test-test-test-backup-202400101000000.tar.gz" --authenticationDatabase=admin

# mysql
mysql --uri="mysql://localhost:27017" --gzip --archive="/backup/test-test-test-backup-202400101000000.tar.gz" --authenticationDatabase=admin

# zip
zip -e test.tar.gz.zip -P 123456 test.tar.gz
unzip -P 123456 test.tar.gz.zip

# docker
docker build -t exmaple/mysql-backup:main .
docker push exmaple/mysql-backup:main
```
