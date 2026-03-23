import concurrent
import multiprocessing
import time
from datetime import datetime
import akshare as ak
from pymongo import MongoClient
from unittest.mock import patch
import requests
import schedule
from utils import get_proxy
from functools import partial
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
from pebble import ProcessPool
from concurrent.futures import TimeoutError as PebbleTimeout


def process_stock_data(code, proxy, db, date):
    """处理单个股票的数据获取和存储"""
    try:
        # 创建一个带代理的 session
        session = requests.Session()
        session.proxies.update(proxy)
        # 用 mock patch 替换 requests.get 为 session.get

        timeout_get = partial(session.get, timeout=10)
        with patch('requests.get', new=timeout_get):
            daily_data = ak.stock_zh_a_hist_min_em(
                symbol=code,
                start_date=f'{date} 09:00:00',  # TODO 0407
                end_date=f'{date} 15:30:00',    # TODO 0407
                period='5',
                adjust='qfq'
            )

        if daily_data.empty:
            return

        latest_date = datetime.strptime(daily_data['时间'].max(), "%Y-%m-%d %H:%M:%S").date()
        current_time = datetime.now().date()
        if latest_date < current_time:
            return

        # 将 DataFrame 转换为字典
        data_dict = daily_data.to_dict(orient='records')

        # 检查对应股票代码的集合
        collection = db[code]
        date_str = date
        existing_doc = collection.find_one({'date': date_str})
        if existing_doc:
            # 存在则覆盖数据
            collection.update_one(
                {'date': date_str},
                {'$set': {'daily_data': data_dict}},
                upsert=True
            )
            print(f"成功覆盖 {code} 在 {date} 的分钟数据")
        else:
            document = {
                'date': date_str,
                'daily_data': data_dict,
            }
            collection.insert_one(document)
    except requests.exceptions.RequestException as e:
        print(f"代码 {code} 网络请求失败: {e}")
        raise
    except Exception as e:
        print(f"获取代码 {code} 的分钟数据时出错: {e}")
        raise


def process_stock_with_own_connection(code, mongo_uri, db_name, date):
    """每个进程自己创建连接并处理股票数据"""
    # 创建独立的MongoDB连接
    client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                maxPoolSize=10000
            )
    db = client[db_name]

    try:
        proxy = get_proxy()[0]  # 每个进程独立获取代理
        process_stock_data(code, proxy, db, date)
    except Exception as e:
        print(f"进程 {os.getpid()} 处理股票 {code} 出错: {e}")
        raise
    finally:
        client.close()


def load_stock_codes(file_path):
    """从文件加载股票代码"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return [line.strip()[2:] for line in file if line.strip()]


def get_today_trading_date():
    """获取当天的交易日（非交易日返回None）"""
    today = datetime.now().date()
    try:
        calendar_df = ak.tool_trade_date_hist_sina()
        if today in calendar_df['trade_date'].tolist():
            return today.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"获取交易日历失败: {str(e)}")
        return None


def scheduled_task(stock_codes, mongo_uri, db_name, num_workers, max_timeout=60, max_retries=3):
    """定时任务：使用 Pebble 进程池处理股票数据，支持超时与自动终止"""
    date = get_today_trading_date()
    if not date:
        print("今天不是交易日，跳过处理")
        return

    print(f"开始处理 {len(stock_codes)} 个股票代码，使用 {num_workers} 个进程")
    retry_list = []

    def submit_tasks(codes):
        results = []
        with ProcessPool(max_workers=num_workers) as pool:
            futures = {
                pool.schedule(
                    process_stock_with_own_connection,
                    args=[code, mongo_uri, db_name, date],
                    timeout=max_timeout
                ): code for code in codes
            }

            for future in futures:
                code = futures[future]
                try:
                    future.result()
                    print(f"成功处理股票 {code}")
                except PebbleTimeout:
                    print(f"股票 {code} 处理超时")
                    retry_list.append(code)
                except Exception as e:
                    print(f"股票 {code} 出错了: {e}")
                    retry_list.append(code)

    # 初次执行
    submit_tasks(stock_codes)

    # 重试执行
    for retry in range(max_retries):
        if not retry_list:
            file_path = "./perfect.txt"
            current_date = datetime.now().strftime("%Y-%m-%d")
            content = f"{current_date}: 今日所有股票任务均成功完成"
            with open(file_path, "a", encoding="utf-8") as file:
                file.write(content)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            break
        print(f"正在进行第 {retry + 1} 次重试，任务数: {len(retry_list)}")
        time.sleep(3)
        current_retry = retry_list
        retry_list = []
        submit_tasks(current_retry)

    if retry_list:
        print(f"以下股票任务最终仍失败: {retry_list}")
        file_path = "./retry.txt"  # 文件路径
        current_date = datetime.now().strftime("%Y-%m-%d")
        # 目标字符串格式
        content = f"{current_date}：{retry_list}"
        # 写入到文件（如果文件不存在会自动创建）
        with open(file_path, "a", encoding="utf-8") as file:
            file.write(content)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())


def main():
    # MongoDB连接参数
    mongo_uri = ''
    db_name = ''

    # 加载股票代码
    stock_codes = load_stock_codes('./stock_codes.txt')
    num_workers = 32  # 工作进程数量

    # 设置定时任务（每天16:00运行）
    schedule.every().day.at("16:00").do(
        scheduled_task,
        stock_codes=stock_codes,
        mongo_uri=mongo_uri,
        db_name=db_name,
        num_workers=num_workers,
        max_timeout=30,
        max_retries=6
        )

    # 如果需要持续运行以支持定时任务，取消注释下面的代码
    # t = time.time()
    # # 初始运行一次
    # scheduled_task(
    #     stock_codes=stock_codes,
    #     mongo_uri=mongo_uri,
    #     db_name=db_name,
    #     num_workers=num_workers,
    #     max_timeout=10,
    #     max_retries=3
    # )
    # print(time.time() - t)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("程序被手动终止")


if __name__ == '__main__':
    # 设置多进程启动方法
    multiprocessing.set_start_method('spawn')  # 使用spawn替代fork以避免潜在问题
    main()
