# akshare-stock-data-fetcher

> 基于 [AKShare](https://github.com/akfamily/akshare) 的 A 股行情数据批量采集工具，支持分钟线历史数据、实时行情快照，内置代理轮转、MongoDB 持久化存储与定时调度，开箱即用。

English | [中文](#中文说明)

---

## ✨ Features

- **分钟线历史数据**：批量抓取全市场 A 股 5 分钟 K 线，多进程并行 + 超时自动重试
- **实时行情快照**：定时抓取 `stock_zh_a_spot_em` 全量行情，自动写入 MongoDB
- **代理轮转**：内置健壮的代理池管理，支持多代理轮转 + 直连兜底，彻底解决 AKShare 被限频/封 IP 问题
- **交易日判断**：自动跳过非交易日，无需手动维护日历
- **股票代码同步**：每日自动更新全量股票代码到本地文件
- **定时调度**：基于 `schedule` 库，支持任意时间点触发

---

## 📁 Project Structure

```
akshare-stock-data-fetcher/
├── get_stock_code_every_day.py      # 每日同步全量股票代码到 stock_codes.txt
├── stock_zh_a_hist_min_em.py        # 批量抓取分钟线历史数据 → MongoDB（多进程 + 重试）
├── stock_zh_a_spot_em.py            # 定时抓取实时行情快照 → MongoDB（基础代理版）
├── stock_zh_a_spot_em_proxy_strength.py  # 定时抓取实时行情快照 → MongoDB（强代理轮转版）
├── utils.py                         # 代理获取 & 通用工具（分钟线专用）
├── utils_spot.py                    # 代理获取 & 通用工具（实时行情专用）
├── utils_spot1.py                   # 精简版代理工具
├── stock_codes.txt                  # 全量 A 股代码（运行后自动生成）
└── requirements.txt
```

---

## 🚀 Quick Start

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置代理（可选但强烈推荐）

在 `utils.py` / `utils_spot.py` / `utils_spot1.py` 中，将以下占位符替换为你自己的代理 API 地址：

```python
proxy_ips = requests.get('代理ip获取地址').text
```

> 推荐使用按量付费的动态住宅代理（如 [极量IP](https://www.juliangip.com)、[快代理](https://www.kuaidaili.com) 等），返回格式为 `ip:port:user:password`。
>
> 如果不使用代理，`stock_zh_a_spot_em_proxy_strength.py` 的 `build_rotating_get` 中已内置 `include_direct=True` 直连兜底，可在低频场景下直接使用。

### 3. 配置 MongoDB

在各主脚本的 `__main__` 块中填入你的 MongoDB 连接信息：

```python
client = MongoClient('mongodb://localhost:27017/')
db = client['stock_data']
```

### 4. 同步股票代码

```bash
python get_stock_code_every_day.py
```

生成 `stock_codes.txt`，供分钟线抓取脚本使用。

### 5. 抓取分钟线历史数据

```bash
python stock_zh_a_hist_min_em.py
```

默认每天 `16:00` 触发，抓取全市场当日 5 分钟 K 线并存入 MongoDB，支持失败自动重试（默认重试 6 次）。

### 6. 抓取实时行情快照

**基础版（简单代理）：**
```bash
python stock_zh_a_spot_em.py
```

**强代理轮转版（推荐用于生产环境）：**
```bash
python stock_zh_a_spot_em_proxy_strength.py
```

默认每天 `15:50` 触发。

---

## ⚙️ Configuration

| 参数 | 位置 | 说明 |
|------|------|------|
| `num_workers` | `stock_zh_a_hist_min_em.py` | 并行进程数，默认 32，按机器性能调整 |
| `max_timeout` | `scheduled_task()` | 单只股票最长处理时间（秒），默认 30 |
| `max_retries` | `scheduled_task()` | 失败重试次数，默认 6 |
| `total_ak_retries` | `stock_zh_a_spot_em_proxy_strength.py` | AKShare 调用重试次数，默认 3 |
| `schedule time` | 各主脚本 `__main__` | 定时触发时间，按需修改 |

---

## 🔧 Why Proxy?

AKShare 底层直接请求东财等数据源，高频批量请求容易触发限流（429）或封 IP。本项目的代理方案：

1. 请求前动态从代理 API 获取最新 IP
2. 多代理顺序轮转，失败自动切换
3. 支持直连兜底（`include_direct=True`）
4. 内置 `urllib3.Retry` 应对 429/5xx 自动退避重试
5. 使用 `unittest.mock.patch` 无侵入地替换 AKShare 内部的 `requests.get`，无需修改 AKShare 源码

---

## 📦 Dependencies

- [akshare](https://github.com/akfamily/akshare) — A 股数据接口
- [pymongo](https://pymongo.readthedocs.io/) — MongoDB 驱动
- [schedule](https://github.com/dbader/schedule) — 定时任务
- [pebble](https://github.com/noxdafox/pebble) — 支持超时的进程池
- requests, pandas

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 中文说明

### 解决了什么问题？

使用 AKShare 批量拉取数据时，大家最常遇到的痛点：

- **被限速 / 封 IP**：大批量请求东财接口，很快触发 429 或连接超时
- **无法定时自动化**：需要手动判断交易日、手动触发
- **进程超时卡死**：部分股票请求长时间无响应，导致整个批次阻塞
- **数据重复/丢失**：没有 upsert 逻辑，重跑时要么报错要么数据混乱

本项目逐一解决了上述问题，可以直接复用到你自己的量化数据管道中。

### 贡献 / 问题反馈

欢迎提 Issue 或 PR！如果这个项目对你有帮助，请给个 ⭐️ 支持一下。
