import time
import requests
from datetime import datetime
import akshare as ak
import schedule
from pymongo import MongoClient
from unittest.mock import patch
from functools import partial
from utils_spot import get_proxy

def get_today_trading_date():
    """获取当天的交易日（非交易日返回None）"""
    today = datetime.now().date()
    try:
        calendar_df = ak.tool_trade_date_hist_sina()
        if today.strftime("%Y-%m-%d") in calendar_df['trade_date'].astype(str).tolist():
            return today.strftime("%Y-%m-%d")
        return None
    except Exception as e:
        print(f"获取交易日历失败: {str(e)}")
        return None

def execute_stock_zh_a_spot_em(db):
    """执行股票数据抓取与存储"""
    # 首先检查今天是否为交易日
    date = get_today_trading_date()
    if not date:
        print(f"{datetime.now()} 今天不是交易日，跳过处理")
        return

    try:
        proxy = get_proxy()[0]
        session = requests.Session()
        session.proxies.update(proxy)

          # 用带代理与超时的 session.get 覆盖 requests.get
        timeout_get = partial(session.get, timeout=10)
        with patch('requests.get', new=timeout_get):
            stock_df = ak.stock_zh_a_spot_em()

        if stock_df is None or stock_df.empty:
            raise ValueError("未获取到数据")

        cleaned_df = stock_df.drop(columns=['序号'], errors='ignore')
        grouped = cleaned_df.groupby('代码')
        date_str = datetime.now().strftime("%Y-%m-%d")

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
                    print(f"成功更新股票 {stock_code} 的当日数据")
                else:
                    document = {
                        'date': date_str,
                        'daily_data': data_dict,
                    }
                    collection.insert_one(document)
                    print(f"成功插入股票{stock_code}的当日数据")
            except Exception as e:
                print(f"股票 {stock_code} 处理失败: {str(e)}")
                continue
        print(f"{datetime.now()} 数据更新完成，共处理 {len(grouped)} 只股票")
    except Exception as e:
        print(f"主流程异常: {str(e)}")


if __name__ == '__main__':
    # 使用与历史数据相同的数据库配置
    client = MongoClient('')
    db = client['']  # 确保与历史数据库名称一致

    # try:
    #     # 立即执行数据抓取和存储
    #     execute_stock_zh_a_spot_em(db)
    #     print("数据处理完成，程序将退出")
    # except Exception as e:
    #     print(f"程序异常: {str(e)}")
    # finally:
    #     # 确保数据库连接关闭
    #     client.close()

    # 设置定时任务
    schedule.every().day.at("15:50").do(execute_stock_zh_a_spot_em, db)

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
    except KeyboardInterrupt:
        print("程序终止")
    finally:
        client.close()