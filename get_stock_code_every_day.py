import akshare as ak
import schedule
from datetime import datetime
import time
import os

def get_stock_codes():
    """获取股票代码并保存到文件"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    stock_zh_a_spot_df = ak.stock_zh_a_spot()
    code_column = stock_zh_a_spot_df['代码']
    with open('stock_codes.txt', 'w', encoding='utf-8') as file:
        for code in code_column:
            file.write(str(code) + '\n')
        file.flush()
        os.fsync(file.fileno())
    print(f"今日:{current_date}股票代码保存成功")

    with open('update_stock_codes_log.txt', 'a', encoding='utf-8') as log_file:
        current_date = datetime.now().strftime("%Y-%m-%d")
        log_file.write(f"{current_date}: 更新股票代码成功，共{len(code_column)}条\n")
        log_file.flush()
        os.fsync(log_file.fileno())

if __name__ == '__main__':
    get_stock_codes()
    # schedule.every().day.at("15:30").do(get_stock_codes)
    # try:
    #     while True:
    #         schedule.run_pending()
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     print("程序被手动终止")