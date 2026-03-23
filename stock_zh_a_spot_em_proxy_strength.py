from datetime import datetime
import akshare as ak
from pymongo import MongoClient
from utils_spot1 import get_proxy
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import (
    ProxyError, ConnectTimeout, ReadTimeout, SSLError,
    ConnectionError, ChunkedEncodingError
)
from unittest.mock import patch
import requests
import traceback
import random
import time


def safe_get_proxy():
    """安全获取代理列表：异常或空值一律返回 []，并规整成 list[dict] 结构。"""
    try:
        proxies = get_proxy()
        if not proxies:
            return []
        if isinstance(proxies, dict):
            return [proxies]
        return list(proxies)
    except Exception as e:
        print(f"{datetime.now()} 获取代理失败，降级直连: {e}")
        traceback.print_exc()
        return []


def build_rotating_get(
    proxies_supplier,
    timeout=20,
    per_proxy_retries=1,
    backoff=(0.3, 0.8),
    include_direct=True,
    max_supplier_refresh=3
):
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

    retriable_exc = (ProxyError, ConnectTimeout, ReadTimeout, SSLError,
                     ConnectionError, ChunkedEncodingError)

    def rotating_get(url, **kwargs):
        last_exc = None

        # 可多次刷新代理池（避免某次拿到的代理全部失效）
        for i in range(max_supplier_refresh + 1):
            remaining_refresh = (max_supplier_refresh + 1) - i
            print(f"{datetime.now()} 开始本轮请求，剩余可刷新代理池次数: {remaining_refresh - 1}")
            try:
                proxies_pool = proxies_supplier() or []
            except Exception as e:
                proxies_pool = []
                last_exc = e

            # 追加一次直连兜底
            if include_direct:
                proxies_pool = list(proxies_pool) + [None]

            random.shuffle(proxies_pool)

            for proxy in proxies_pool:
                s = requests.Session()
                try:
                    s.trust_env = False  # 不使用系统环境代理，避免干扰
                    s.headers.update({
                        "User-Agent": ua,
                        "Accept": "*/*",
                        "Connection": "close",
                        "Referer": "https://quote.eastmoney.com/"
                    })
                    if proxy:
                        s.proxies.update(proxy)

                    retry = Retry(
                        total=per_proxy_retries,
                        connect=per_proxy_retries,
                        read=per_proxy_retries,
                        backoff_factor=0.5,
                        status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=["GET"],
                        respect_retry_after_header=True,
                        raise_on_status=False,
                    )
                    adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
                    s.mount("http://", adapter)
                    s.mount("https://", adapter)

                    req_kwargs = dict(kwargs)
                    req_kwargs.setdefault("timeout", timeout)

                    resp = s.get(url, **req_kwargs)
                    resp.raise_for_status()
                    return resp
                except retriable_exc as e:
                    last_exc = e
                    time.sleep(random.uniform(*backoff))
                    print(f"{datetime.now()} 代理 {proxy} 失败，尝试下一个代理...")
                    continue
                finally:
                    try:
                        s.close()
                    except Exception:
                        pass

            print(f"{datetime.now()}所有代理均失败，尝试刷新代理池...")
            time.sleep(random.uniform(*backoff))

        # 所有刷新/尝试都失败
        if last_exc:
            raise last_exc
        raise RuntimeError("请求失败且无可用代理")

    return rotating_get


def get_trading_dates(start_date, end_date):
    """获取指定日期范围内的交易日，返回字符串列表：YYYY-MM-DD"""
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    calendar_df = ak.tool_trade_date_hist_sina()
    trading_dates = calendar_df[calendar_df['trade_date'].between(start_date_dt, end_date_dt)]['trade_date'].tolist()
    return [d.strftime("%Y-%m-%d") for d in trading_dates]


def execute_stock_zh_a_spot_em(start_date, end_date, db, total_ak_retries):
    trading_dates = get_trading_dates(start_date, end_date)
    if not trading_dates:
        print(f"{datetime.now()} 指定日期不在交易日内，跳过处理")
        return
    date_str = trading_dates[0]

    try:
        # 关键：保存原始 requests.get，供获取代理时使用，避免递归
        original_get = requests.get

        def dynamic_proxies_supplier():
            # 在被 patch 的环境里，暂时还原为原始 get 再拉代理
            with patch('requests.get', new=original_get):
                return safe_get_proxy()

        rotating_get = build_rotating_get(
            proxies_supplier=dynamic_proxies_supplier,
            timeout=20,
            per_proxy_retries=1,
            backoff=(0.4, 1.0),
            include_direct=False,
            max_supplier_refresh=3
        )

        # 对 ak 调用做总重试，避免单次分页中断直接失败
        last_err = None
        for i in range(total_ak_retries):
            remaining_ak = total_ak_retries - i
            print(f"{datetime.now()} 开始第 {i + 1} 次 ak 调用重试，本次之后剩余次数: {remaining_ak - 1}")
            try:
                with patch('requests.get', new=rotating_get):
                    stock_df = ak.stock_zh_a_spot_em()
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(random.uniform(0.6, 1.2))

        if last_err:
            raise last_err

        if stock_df is None or stock_df.empty:
            raise ValueError("未获取到数据")

        cleaned_df = stock_df.drop(columns=['序号'], errors='ignore')
        grouped = cleaned_df.groupby('代码')

        for stock_code, group in grouped:
            try:
                collection = db[stock_code]
                data_dict = group.to_dict(orient='records')

                existing_doc = collection.find_one({'date': date_str})
                if existing_doc:
                    collection.update_one(
                        {'date': date_str},
                        {'$set': {'daily_data': data_dict}},
                        upsert=True
                    )
                    print(f"股票数据覆盖成功：{stock_code}")
                else:
                    collection.insert_one({'date': date_str, 'daily_data': data_dict})
                    print(f"插入股票数据成功：{stock_code}")
            except Exception as e:
                print(f"处理失败 {stock_code}: {str(e)}")
                continue

        print(f"{date_str} 数据更新完成，共处理 {len(grouped)} 只股票")
    except Exception as e:
        print(f"主流程异常: {str(e)}")
        traceback.print_exc()


if __name__ == '__main__':
    client = MongoClient('')
    db = client['']

    start_date = "2026-03-23"
    end_date = "2026-03-23"
    total_ak_retries = 3

    execute_stock_zh_a_spot_em(
        start_date=start_date,
        end_date=end_date,
        db=db,
        total_ak_retries=total_ak_retries
    )

    client.close()
