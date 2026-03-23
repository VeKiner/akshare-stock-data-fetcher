import json
import random
import time
from os import close
from unittest.mock import patch
from urllib.parse import urlparse
import akshare as ak
import requests
import pandas as pd


def get_proxy():
    ips = []
    while len(ips) < 1:
        proxy_ips = requests.get(
            '代理ip获取地址').text
        proxy_list = proxy_ips.strip().split(":")
        proxy_ip = f"{proxy_list[0]}:{proxy_list[1]}"
        username = proxy_list[2]
        password = proxy_list[3]
        proxies = {
            "http": f"http://{username}:{password}@{proxy_ip}/",
            "https": f"http://{username}:{password}@{proxy_ip}/",
        }

        # 要访问的目标网页
        try:
            target_url = "https://82.push2.eastmoney.com/api/qt/clist/get"
            user_agent_list = [
                "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; …) Gecko/20100101 Firefox/61.0",
                "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.186 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36",
                "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.101 Safari/537.36",
                "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
                "Mozilla/5.0 (Macintosh; U; PPC Mac OS X 10.5; en-US; rv:1.9.2.15) Gecko/20110303 Firefox/3.6.15",
            ]
            headers = {
                "User-Agent": random.choice(user_agent_list),
                'Connection': 'close'
            }
            # 使用代理IP发送请求
            time.sleep(5)
            r = requests.get(target_url, proxies=proxies, headers=headers, timeout=5)
            if r.status_code == 200:
                ips.append(proxies)
        except Exception as e:
            print(f"跳过无效代理 {proxies}，错误原因: {e}")
            continue

    return ips


if __name__ == '__main__':
    t = time.time()
    r = get_proxy()
    print(time.time() - t)