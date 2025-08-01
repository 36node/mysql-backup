import os
import re
import sys
from datetime import datetime, timedelta
import subprocess
import boto3
from botocore.client import Config

# 数据库还原

DEFAULT_MYSQL_PORT = 3306
DEFAULT_BACKUP_PATH = "/backup"

DEFAULT_S3_PREFIX = ""

must_inputs = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PWD"]
other_inputs = [
    "MYSQL_PORT",
    "MYSQL_DB",
    "FILE_PREFIX",
    "BACKUP_PATH",
    "BACKUP_PWD",
    # S3 CONFIG
    "S3_ENABLE",
    "S3_EP",
    "S3_EP_VIRTUAL",
    "S3_ACCESS_KEY",
    "S3_ACCESS_SECRET",
    "S3_BUCKET",
    "S3_PREFIX",
    "S3_REGION",
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
mysql_db = os.environ["MYSQL_DB"] if check_var("MYSQL_DB") else None
backup_path = (
    os.environ["BACKUP_PATH"] if check_var("BACKUP_PATH") else DEFAULT_BACKUP_PATH
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

date = (datetime.now() + timedelta(hours=8)).strftime("%Y%m%d%H%M%S")


def get_files(compiled_regex):
    # 列出备份文件夹中所有的文件
    all_files = os.listdir(backup_path)

    # 筛选出符合正则表达式的文件
    matched_files = [file for file in all_files if compiled_regex.match(file)]

    # 根据文件名排序（这使得最新的备份文件位于列表的末尾）
    matched_files.sort(reverse=True)
    return matched_files


def get_keys_from_s3(client, compiled_regex):
    list_prefix = f"{s3_prefix}/" if s3_prefix else ""
    resp = client.list_objects_v2(Bucket=s3_bucket, Prefix=list_prefix, Delimiter="/")
    if "Contents" in resp:
        objects = resp["Contents"]

        keys = [
            object["Key"] for object in objects if compiled_regex.match(object["Key"])
        ]

        if keys:
            # 根据文件名排序（这使得最新的备份文件位于列表的末尾）
            keys.sort(reverse=True)
            return keys
    raise Exception("没有可用的备份")


def download_file(client, key):
    file_name = os.path.basename(key)
    save_path = f"/tmp/{file_name}"
    client.download_file(s3_bucket, key, save_path)
    return save_path


def restore_file(file_path):
    is_crypt_file = file_path.endswith(".crypt")
    restore_path = file_path if not is_crypt_file else file_path[:-6]

    if is_crypt_file and not backup_pwd:
        print("need set BACKUP_PWD")
        sys.exit()

    if is_crypt_file and backup_pwd:
        # 先解密
        unzip_path = os.path.dirname(file_path)
        # -o 覆盖已有文件，-j 不保留文件夹
        subprocess.call(
            f"unzip -P {backup_pwd} -oj {file_path} -d {unzip_path}", shell=True
        )

    # 恢复数据
    cmd = f'mysql -h {mysql_host} -P {mysql_port} -u {mysql_user} -p"{mysql_pwd}" < {restore_path}'
    if mysql_db:
        cmd = f'mysql -h {mysql_host} -P {mysql_port} -u {mysql_user} -p"{mysql_pwd}" {mysql_db} < {restore_path}'

    subprocess.call(cmd, shell=True)

    if is_crypt_file and backup_pwd:
        # 删除解密文件
        os.remove(restore_path)


try:
    # 构造正则表达式
    regex_pattern = f"^.*(\\d{{14}})\\.sql(\\.crypt)?$"
    compiled_regex = re.compile(regex_pattern)

    client = None
    # 1. 获取备份文件列表
    if s3_enable:
        # s3 config
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
        backup_files = get_keys_from_s3(client, compiled_regex)
    else:
        backup_files = get_files(compiled_regex)

    input_cmd = "请选择要还原的备份文件：\n"
    for index, item in enumerate(backup_files):
        input_cmd += f"{index + 1}. {item}\n"
    value = input(input_cmd)

    if s3_enable:
        # 需要下载文件
        file = download_file(client, backup_files[int(value) - 1])
    else:
        file = f"{backup_path}/{backup_files[int(value) - 1]}"

    restore_file(file)

    if s3_enable:
        # 删除临时文件
        os.remove(file)

    print("script end")
except Exception as e:
    print("restore error:", e)
    sys.exit()
