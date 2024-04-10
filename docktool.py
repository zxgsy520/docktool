#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import logging
import argparse

import smtplib
from email.header import Header
from email.mime.text import MIMEText

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) #初始化时，如果没指定level，那么level的默认级别为WARNING
__version__ = "1.0.0"
__author__ = ("Xingguo Zhang",)
__email__ = "invicoun@foxmail.com"
__all__ = []


SEML = ""	#发送人
REML = ""	#收件人
PASSWORD = ""	#发送人密码


def convert_time(string):

    """将时间单位统一为秒"""
    stime = string.lower()

    if stime.endswith("d"):
        stime, unit = stime.split("d", 1)
        stime = float(stime)*216000
    elif stime.endswith("h"):
        stime, unit = stime.split("h", 1)
        stime = float(stime)*3600
    elif stime.endswith("m") or stime.endswith("min"):
        stime, unit = stime.split("m", 1)
        stime = float(stime)*60
    elif stime.endswith("s"):
        stime, unit = stime.split("s", 1)
        stime = float(stime)
    else:
        try:
            stime = float(stime)
        except:
            raise Exception("Size %s input error" % string)

    return stime


def size2gb(string):

    """将文件大小统一为GB"""
    string = string.lower()

    if " " in string:
       string = string.split(" ", 1)[0]
    if string.endswith("kb") or string.endswith("k"):
       fsize, unit = string.split("k", 1)
       fsize = float(fsize)/(1024*1024)
    elif string.endswith("mb") or string.endswith("m"):
       fsize, unit = string.split("m", 1)
       fsize = float(fsize)/1024
    elif string.endswith("gb") or string.endswith("g"):
       fsize, unit = string.split("g", 1)
       fsize = float(fsize)
    elif string.endswith("b"):
       fsize, unit = string.split("b", 1)
       fsize = float(fsize)/(1024*1024*1024)
    else:
       try:
           fsize = float(string)/(1024*1024*1024)
       except:
           raise Exception("Size %s input error" % string)

    return fsize


def stat_cache():

    """统计docker占用的空间大小"""
    r = os.popen("docker system df")
    csum = 0 #docker占用总的存储大小
    rsum = 0 #docker可清理的存储大小（可回收）

    for n, line in enumerate(r):
        line = line.strip()
        if line.startswith("TYPE") or not line:
            continue
        line = re.sub(r"\s{2,}", "\t", line) #将2个以上的空格替换为制表符
        line = line.split("\t")
        csum += size2gb(line[3])
        rsum += size2gb(line[4])
    LOG.info("Docker occupies an empty size of {:,.2f}Gb".format(csum))

    return csum, rsum


def monitor_disk_storage(dname="/dev/vda1"):

    """查看磁盘的使用情况"""
    dsize = 0 #磁盘大小
    usize = 0 #使用率

    r = os.popen("df -h")
    for n, line in enumerate(r):
        line = line.strip()
        line = re.sub(r"\s{2,}", "\t", line) #将2个以上的空格替换为制表符
        line = line.split("\t")
        if line[0] == dname:
            dsize, usize = size2gb(line[1]), size2gb(line[2])
            break
    LOG.info("磁盘{0}剩余存储为{1:,.2f}Gb.".format(dname, dsize-usize))

    return dsize, usize


def send_mail(title="服务器云存储不足", content="服务器云存储不足"):

    message = MIMEText(content, "plain", "utf-8")
    #创建邮件对象和设置邮件内容
    message["Subject"] = Header(title, "utf-8")
    message["From"] = Header(SEML)
    message["To"] = Header(REML)

    #开启发信服务，这里使用的是加密传输
    server = smtplib.SMTP_SSL(host="smtp.163.com")
    server.connect("smtp.163.com", 465) #常见的SMTP端口号是25、465或587
    #登录发信邮箱
    server.login(SEML, PASSWORD)
    try:
        #发送邮件
        server.sendmail(SEML, REML, message.as_string())
    except:
        LOG.info("Email sent Failed!")
    else:
        LOG.info("Email sent successfully!")
    #关闭服务器
    server.quit()

    return 0


def clear_cache(args):

    sleep_time = convert_time(args.sleep_time)
    n = 0
    while True:
        n += 1
        cmd = 'docker builder prune --filter "until=%s"' % args.cache_time #清理缓存命令
        LOG.info(cmd)
        LOG.info("进行第%s次清理." % n)
        os.popen(cmd) #运行清理缓存
        cache, rsum = stat_cache()
        dsize, usize = monitor_disk_storage(dname=args.disk_name)
        if usize >= dsize*0.95: #剩余存储小于5%，需要进行警告
            stat_cache(title="服务器云存储不足",
            content="服务器云存储不足，磁盘大小为{0:,.2f}Gb，使用了{1:,.2f}Gb，剩余空间为{2:,.2f}%，docker占用{3:,.2f}Gb，请尽快清理。".format(
                dsize, usize, (dsize-usize)*100.0/dsize, rsum))
        elif usize >= dsize*0.999: #存储即将爆了，使用紧急预案
            os.popen('docker builder prune --filter "until=0.5h"')
            #os.popen("docker system prune --all")
            #注意不要轻易使用--all，使用--all将清楚所有没有在使用的镜像（长期不使用的镜像建议做好备份）。
            stat_cache(title="服务器云存储严重不足",
            content="服务器云存储严重不足，磁盘大小为{0:,.2f}Gb，使用了{1:,.2f}Gb，剩余空间为{2:,.2f}%，docker占用{3:,.2f}Gb，使用紧急预案。".format(
                dsize, usize, (dsize-usize)*100.0/dsize, rsum))
        else:
            pass
        time.sleep(sleep_time) #进行睡眠

    return 0


def add_clear_cache_args(parser):

    parser.add_argument("-st", "--sleep_time", metavar="STR", type=str, default="12h",
        help="Set cleaning interval time, default=12h")
    parser.add_argument("-ct", "--cache_time", metavar="STR", type=str, default="48h",
        help="Set retention period, default=48h")
    parser.add_argument("-dn", "--disk_name", metavar="STR", type=str, default="/dev/vda1",
        help="Set the disk name where the Docker is located, default=/dev/vda1")

    return parser


def add_docktool_parser(parser):

    subparsers = parser.add_subparsers(
        title="command",
        dest="commands")
    subparsers.required = True

    clear_cache_parser = subparsers.add_parser("clear_cache",
        help="Regularly cleaning cache in Docker")
    clear_cache_parser = add_clear_cache_args(clear_cache_parser)
    clear_cache_parser.set_defaults(func=clear_cache)

    return parser


def main():

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
name:
docktool: Docker monitoring tool

version: %s
contact:  %s <%s>\
        """ % (__version__, " ".join(__author__), __email__))

    parser = add_docktool_parser(parser)
    args = parser.parse_args()

    args.func(args)

    return parser.parse_args()


if __name__ == "__main__":

    main()
