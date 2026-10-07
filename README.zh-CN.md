<p align="center">
  <img src="assets/linshen.png" width="128" alt="TwinTitle">
</p>

<h1 align="center">TwinTitle</h1>

<p align="center">
  <b>同题猎手</b> · 按公司对外标题查钓鱼 / 像真站<br>
  <i>by 林神</i>
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">中文</a> · <a href="CHANGELOG.md">更新日志</a>
</p>

<p align="center">
  <img src="assets/screenshot.png" alt="TwinTitle 运行界面">
</p>

---

## 这是什么

填一个**公司全称**，TwinTitle 会：

1. 用公开备案反查官网根域
2. 探官网标题，fuzz 像真站关键字
3. 用 FOFA 搜精确 title 和关键字
4. 对命中站探活、查备案、改后缀看是否注册
5. 导出带判定的 xlsx：结果 / 分析 / 查询语句

英文名 **TwinTitle**，界面中文名 **同题猎手**。

## 管线

```
公司全称
  → icplishi.com/company/{name}/     公开备案反查根域
  → www / apex 探官网标题
  → 标题 fuzz 像真站关键字
  → FOFA title="…" 精确 + 关键字扩搜
  → httpx 探活；Clash 假 IP 再 curl --noproxy --resolve
  → 像真站走 chinaz 备案
  → 根名改 .com / .net / .org / .top / .cn / .com.cn 看是否注册
  → 判定 + xlsx
```

根域必须是备案域名。邮箱、`@`、`0.0.0.0`、公共邮箱商一律丢掉。

## 功能

- GUI（tkinter）+ 无头 CLI
- 只填公司全称就能跑，根域 / URL / 关键字可空
- 公开备案反查，不用在本机部署 ICP 服务
- FOFA 官方 API（VIP 间隔约 4 秒）
- 探活忽略 Clash TUN 假 IP `198.18.0.0/15`
- 丢掉标题不含公司名 / 关键字的资讯中心、邮箱模板
- 官网只留一条活体，判定为 **自有**
- 随包 `httpx.exe` / `curl.exe` / FOFA / chinaz

本工具不做：Hunter、Quake、WHOIS、ENScan、爱企查。

## 环境

- Windows
- Python 3.8+（带 tkinter）
- FOFA API Key（`official` 模式）

```text
pip install -r requirements.txt
```

当前依赖：`openpyxl>=3.1.0`。

## 快速开始

1. 复制配置：

```text
copy config.example.json config.json
```

2. 在 `config.json` 填 FOFA Key（或打开软件点右上角 **配置**）。
3. 双击 `启动.bat`（或 `run.cmd`）。
4. 填 **公司名称**（全称）。根域 / URL / 关键字可空。
5. 点 **开始排查**，结束后导出 xlsx。

配置窗口可以一键探测 FOFA / 代理 / 备案反查是否有效。

**不要把 `config.json` 提交进 git。** 仓库里只留 `config.example.json`。

## 配置

`config.example.json`：

```json
{
  "fofa_key": "在这里填你的 FOFA API KEY",
  "fofa_mode": "official",
  "fofa_interval": 4,
  "proxy": "http://127.0.0.1:7897",
  "proxy_enable": false
}
```

| 字段 | 含义 |
| --- | --- |
| `fofa_key` | FOFA Key。只写本地 `config.json`，禁止进仓库 |
| `fofa_mode` | `official` |
| `fofa_interval` | FOFA 调用间隔秒（VIP 约 4） |
| `proxy` | 可选 HTTP 代理 |
| `proxy_enable` | 默认 `false`。测绘 / 备案反查默认直连；探活始终 `--noproxy` |

## 命令行

```text
python engine.py --validate
python engine.py --title "某某集团有限公司" --out out/result.xlsx
```

| 参数 | 含义 |
| --- | --- |
| `--title` | 公司全称（必填） |
| `--official` | 官网根域，逗号或换行 |
| `--url` | 官网 URL |
| `--alias` | 别名根域 |
| `--keywords` | 扩搜关键字 |
| `--out` | xlsx 路径 |
| `--size` | FOFA 条数（默认 50） |
| `--no-roots` | 跳过备案反查 |
| `--no-probe` | 跳过探活 |
| `--no-icp` | 跳过 chinaz 备案 |
| `--no-suffix` | 跳过改后缀 |
| `--no-keywords` | 跳过关键字 FOFA |
| `--validate` | 只测 FOFA 连通 |

## 产出

xlsx 三张表：

| 表 | 内容 |
| --- | --- |
| 结果 | 判定、URL、FOFA标题、活体标题、IP、端口、存活、备案号、备案主体、查询语句、说明 |
| 分析 | 排查摘要 |
| 查询语句 | 每条 FOFA 语句 + total / 返回 / 错误 |

默认目录：`out\`。

### 判定

| 标签 | 含义 |
| --- | --- |
| 可疑钓鱼 | 第三方活体，同标题 / 像真站 |
| 可疑-被拦 | 像真站，被 WAF / 403 / 挑战页拦住 |
| 可疑-不通 | FOFA 有记录，现在不通 |
| 需人工 | 说不清，要人看 |
| 测绘过期 | 还在 FOFA 索引里，已经不活 |
| 博彩/冒备案 | 博彩或假备案 |
| 自有 | 官网活体 |
| 排除 | 无关 |
| 未见注册 | 别名后缀没注册 |

FOFA 某条语句返回 0，只说明当前索引空，不说明世界上没有这个站。

## 目录

```text
TwinTitle/
  启动.bat / run.cmd     图形界面入口
  ui.py                  界面
  engine.py              引擎 + 无头 CLI
  config.example.json    配置模板
  requirements.txt
  assets/linshen.ico     林神品牌图标
  assets/screenshot.png  运行截图
  tools/
    httpx.exe            批量探活（projectdiscovery 1.2.4）
    curl.exe             钉测绘 IP 探活（TUN 污染 DNS 时）
    lib/fofa_api.py
    lib/domain_icp.py    chinaz 备案（域名 → 备案号）
  out/                   导出（gitignore）
```

## 说明

- 公司名 → 根域只走 `GET https://icplishi.com/company/{urlencoded 全称}/`
- Clash TUN 若把 `icplishi.com` 解析成 `198.18.0.0/15`，引擎用阿里 / 360 DoH 拿真 IP，再 `curl --http1.1 --resolve`
- 探活不走代理
- `config.json`、排查结果不要进 git，见 `.gitignore`

## 作者

**林神**

所谓的大佬，一辈子都以为自己是小白。

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。

### v1.0.0 — 2026-10-06

- 首发 TwinTitle（同题猎手）
- 公司全称 → icplishi 公开备案反查根域
- 官网探活 + 标题 fuzz 像真站关键字
- FOFA 精确 title / 关键字扩搜
- httpx 探活；Clash TUN 假 IP 走 curl `--noproxy --resolve`
- 像真站查 chinaz 备案；根域改后缀看是否注册
- GUI：林神图标、滚动标语、by 林神、配置一键探测
- 导出 xlsx 三张表（结果 / 分析 / 查询语句）
- `config.json`（FOFA Key）不进仓库
