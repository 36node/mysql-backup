import os
import re
import sys
from datetime import datetime, timedelta
import subprocess
import boto3
from botocore.client import Config

# 数据库清理备份脚本
# 1. 按要求备份数据，并保存到指定路径
# 2. 清理备份，保留最近的若干份
# 3. 将备份文件上传到 S3，并清理 S3 上的多余备份文件

DEFAULT_MYSQL_PORT = 3306
DEFAULT_FILE_PREFIX = ""
DEFAULT_BACKUP_PATH = "/backup"
DEFAULT_BACKUP_SAVE_NUMS = 3

DEFAULT_S3_PREFIX = ""

must_inputs = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PWD"]
other_inputs = [
    "MYSQL_PORT",
    "MYSQL_DBS",
    "MYSQL_TABLES",
    "MYSQL_EXCLUDE_TABLES",
    "MYSQL_OTHER_CMD",
    "FILE_PREFIX",
    "BACKUP_PATH",
    "BACKUP_SAVE_NUMS",
    "BACKUP_PWD",
    # S3 CONFIG
    "S3_ENABLE",
    "S3_EP",
    "S3_EP_VIRTUAL",
    "S3_ACCESS_KEY",
    "S3_ACCESS_SECRET",
    "S3_REGION",
    "S3_BUCKET",
    "S3_PREFIX",
]

for key in must_inputs:
    if key not in os.environ or os.environ[key] == "":
        print(key, "must set")
        sys.exit()


def check_var(key):
    if key in os.environ and os.environ[key] != "":
        return True
    return False


def check_bool(key):
    if os.environ[key].lower() == "true":
        return True
    return False


# 必填
mysql_host = os.environ["MYSQL_HOST"]
mysql_user = os.environ["MYSQL_USER"]
mysql_pwd = os.environ["MYSQL_PWD"]

# 选填
mysql_port = os.environ["MYSQL_PORT"] if check_var("MYSQL_PORT") else DEFAULT_MYSQL_PORT
mysql_dbs = os.environ["MYSQL_DBS"].split(",") if check_var("MYSQL_DBS") else None
mysql_tables = (
    os.environ["MYSQL_TABLES"].split(",") if check_var("MYSQL_TABLES") else None
)
mysql_exclude_tables = (
    os.environ["MYSQL_EXCLUDE_TABLES"].split(",")
    if check_var("MYSQL_EXCLUDE_TABLES")
    else None
)
mysql_other_cmd = (
    os.environ["MYSQL_OTHER_CMD"].split(",") if check_var("MYSQL_OTHER_CMD") else None
)

file_prefix = (
    os.environ["FILE_PREFIX"] if check_var("FILE_PREFIX") else DEFAULT_FILE_PREFIX
)
backup_path = (
    os.environ["BACKUP_PATH"] if check_var("BACKUP_PATH") else DEFAULT_BACKUP_PATH
)
backup_save_nums = (
    int(os.environ["BACKUP_SAVE_NUMS"])
    if check_var("BACKUP_SAVE_NUMS")
    else DEFAULT_BACKUP_SAVE_NUMS
)
backup_pwd = os.environ["BACKUP_PWD"] if check_var("BACKUP_PWD") else None

s3_enable = check_bool("S3_ENABLE") if check_var("S3_ENABLE") else False
s3_ep = os.environ["S3_EP"] if check_var("S3_EP") else None
s3_ep_virtual = check_bool("S3_EP_VIRTUAL") if check_var("S3_EP_VIRTUAL") else False
s3_access_key = os.environ["S3_ACCESS_KEY"] if check_var("S3_ACCESS_KEY") else None
s3_access_secret = (
    os.environ["S3_ACCESS_SECRET"] if check_var("S3_ACCESS_SECRET") else None
)
s3_bucket = os.environ["S3_BUCKET"] if check_var("S3_BUCKET") else None
s3_prefix = os.environ["S3_PREFIX"] if check_var("S3_PREFIX") else DEFAULT_S3_PREFIX
s3_region = os.environ["S3_REGION"] if check_var("S3_REGION") else None

# 计算当前日期，按照 年月日时分 格式
date = (datetime.now() + timedelta(hours=8)).strftime("%Y%m%d%H%M%S")


def calculate_file_prefix(dbs=None, tables=None, exclude_tables=None, file_prefix=None):
    # 初始化最终的前缀字符串
    final_prefix = ""

    # 检查file_prefix是否非空，如果是则添加到最终前缀
    if file_prefix:
        final_prefix = f"{file_prefix}"

    # 在db存在的基础上构造前缀
    if dbs:
        final_prefix += f"-{'__'.join(dbs)}"

        # 在db存在的情况下构造前缀
        if tables:
            final_prefix += f"-{'__'.join(tables)}"
        elif exclude_tables:
            final_prefix += f"-exclude-{'__'.join(exclude_tables)}"

    if final_prefix:
        # 如果前缀不为空，确保以'-'结尾
        if not final_prefix.endswith("-"):
            final_prefix += "-"

    return final_prefix


def cleanup_files(prefix):
    # 构造正则表达式
    regex_pattern = f"^{re.escape(prefix)}(\\d{{14}})\\.sql(\\.crypt)?$"
    compiled_regex = re.compile(regex_pattern)

    # 列出备份文件夹中所有的文件
    all_files = os.listdir(backup_path)

    # 筛选出符合正则表达式的文件
    matched_files = [file for file in all_files if compiled_regex.match(file)]

    # 根据文件名排序（这使得最新的备份文件位于列表的末尾）
    matched_files.sort()

    # 确定需要删除的文件（保留最后N个文件，这里是backup_save_nums）
    files_to_remove = matched_files[:-backup_save_nums]

    # 删除旧的备份文件
    for file in files_to_remove:
        os.remove(os.path.join(backup_path, file))
        print(f"Deleted old backup file: {file}")


def backup_file(prefix):
    backup_file_name = f"{prefix}{date}.sql"
    # cmd = f"mysqldump -h {mysql_host} -u {mysql_user} -p{mysql_pwd} --all-databases > {backup_path}/{backup_file_name}"
    option = ""
    if not mysql_dbs:
        # 备份所有数据库 mysqldump -h 127.0.0.1 -u root -p"123456" -A
        option = "-A"
    elif len(mysql_dbs) == 1:
        db = mysql_dbs[0]
        # 备份单个数据库
        if mysql_tables:
            # 备份单个数据库下的指定表 mysqldump -h 127.0.0.1 -u root -p"123456" test table1 table2
            option = f"{db} {' '.join(mysql_tables)}"
        elif mysql_exclude_tables:
            # 备份单个数据库下的所有表，排除指定表 mysqldump -h 127.0.0.1 -u root -p"123456" test --ignore-table=test.table1 --ignore-table=test.table2
            option = f"{db} {' '.join(f'--ignore-table={db}.{table}' for table in mysql_exclude_tables)}"
        else:
            # 无其他内容 mysqldump -h 127.0.0.1 -u root -p"123456" test
            option = f"{db}"
    else:
        # 备份多个数据库 mysqldump -h 127.0.0.1 -u root -p"123456" -B test1 test2
        option = f"-B {' '.join(mysql_dbs)}"

    if mysql_other_cmd:
        # 添加其他命令
        option += " " + " ".join(mysql_other_cmd)

    cmd = f'mysqldump -h {mysql_host} -P {mysql_port} -u {mysql_user} -p"{mysql_pwd}" {option} > {backup_path}/{backup_file_name}'
    print(cmd)
    subprocess.call(cmd, shell=True)

    # 加密
    if backup_pwd:
        source = f"{backup_path}/{backup_file_name}"
        subprocess.call(f"zip -e {source}.crypt -P {backup_pwd} {source}", shell=True)
        os.remove(source)


def upload_s3(prefix):
    # config
    config_s3 = {}
    if s3_ep_virtual:
        config_s3["addressing_style"] = "virtual"

    if s3_region:
        config = Config(s3=config_s3, region_name=s3_region)
    else:
        config = Config(s3=config_s3)

    client = boto3.client(
        "s3",
        endpoint_url=s3_ep,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_access_secret,
        config=config,
    )

    # 上传备份文件
    file_name = (
        f"{prefix}{date}.tar.gz.crypt" if backup_pwd else f"{prefix}{date}.tar.gz"
    )
    upload_path = f"{s3_prefix}/{file_name}" if s3_prefix else file_name
    client.upload_file(f"{backup_path}/{file_name}", s3_bucket, upload_path)

    # 清理 S3 上的多余备份文件
    list_prefix = f"{s3_prefix}/" if s3_prefix else ""
    resp = client.list_objects_v2(Bucket=s3_bucket, Prefix=list_prefix, Delimiter="/")
    if "Contents" in resp:
        objects = resp["Contents"]

        file_prefix = f"{list_prefix}{prefix}"
        # 构造正则表达式
        regex_pattern = f"^{re.escape(file_prefix)}(\\d{{14}})\\.tar\\.gz(\\.crypt)?$"
        compiled_regex = re.compile(regex_pattern)
        keys = [
            object["Key"] for object in objects if compiled_regex.match(object["Key"])
        ]

        # 根据文件名排序（这使得最新的备份文件位于列表的末尾）
        keys.sort()

        # 确定需要删除的文件（保留最后N个文件，这里是backup_save_nums）
        keys_to_remove = keys[:-backup_save_nums]

        # 删除旧的备份文件
        if keys_to_remove:
            client.delete_objects(
                Bucket=s3_bucket,
                Delete={"Objects": [{"Key": key} for key in keys_to_remove]},
            )
            print(f"Deleted s3 old backup files: {keys_to_remove}")


try:
    if not os.path.exists(backup_path):
        os.makedirs(backup_path)

    final_prefix = calculate_file_prefix(mysql_dbs, mysql_tables,mysql_exclude_tables, file_prefix)
    print("final_prefix: ", final_prefix)

    # 1. 按要求备份数据，并保存到指定路径
    backup_file(final_prefix)
    print("backup end")

    # 2. 清理备份，保留最近的若干份
    cleanup_files(final_prefix)
    print("cleanup end")

    if s3_enable:
        # 3. 将备份文件上传到 S3，并清理 S3 上的多余备份文件
        upload_s3(final_prefix)
        print("upload s3 end")

    print("script end")

except Exception as e:
    print("backup error:", e)
    sys.exit()
