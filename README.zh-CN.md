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
  <a href="https://github.com/everybelief/TwinTitle/releases/latest"><b>下载 Windows exe</b></a>
</p>

<p align="center">
  <img src="assets/screenshot.png" alt="TwinTitle 运行界面">
</p>

---

填公司全称，一行一个，可批量。工具会反查备案根域、探官网标题、用 FOFA 搜同标题 / 像真站，探活、查备案、改后缀看有没有被人注册，最后导出 xlsx。

```
公司全称
  → icplishi 公开备案反查根域
  → 探官网标题，fuzz 像真站关键字
  → FOFA 精确 title + 关键字
  → 探活；Clash 假 IP 改走 curl
  → 像真站查 chinaz 备案
  → 根名改后缀看是否注册
  → 判定 + xlsx
```

根域必须是备案域名。邮箱、`@`、`0.0.0.0` 一律丢掉。Hunter / Quake / WHOIS / 爱企查不做。

## 使用

不想装 Python：从 [Releases](https://github.com/everybelief/TwinTitle/releases/latest) 下 `TwinTitle.exe`，打开后点 **配置** 填 FOFA Key。

源码：

```text
copy config.example.json config.json
pip install -r requirements.txt
```

双击 `启动.bat`，填公司名称，点开始排查。单家根域 / URL / 关键字可空；批量时每家自己反查。结果按公司、按判定分类，可导出 xlsx。

`config.json` 只放本地，不要提交。

## 配置

```json
{
  "fofa_key": "在这里填你的 FOFA API KEY",
  "fofa_mode": "official",
  "fofa_interval": 2,
  "proxy": "http://127.0.0.1:7897",
  "proxy_enable": false
}
```

| 字段 | 含义 |
| --- | --- |
| `fofa_key` | FOFA Key |
| `fofa_mode` | `official` |
| `fofa_interval` | 调用间隔（秒） |
| `proxy` | 可选代理 |
| `proxy_enable` | 默认关。测绘 / 备案直连；探活始终不走代理 |

## 命令行

```text
python engine.py --validate
python engine.py --title "某某集团有限公司" --out out/result.xlsx
python engine.py --title "甲公司有限公司,乙公司有限公司" --out out/batch.xlsx
```

| 参数 | 含义 |
| --- | --- |
| `--title` | 公司全称，逗号或换行可多家 |
| `--official` | 官网根域 |
| `--url` | 官网 URL |
| `--alias` | 别名根域 |
| `--keywords` | 扩搜关键字 |
| `--out` | xlsx 路径 |
| `--size` | FOFA 条数，默认 50 |
| `--no-roots` | 不反查备案 |
| `--no-probe` | 不探活 |
| `--no-icp` | 不查 chinaz |
| `--no-suffix` | 不改后缀 |
| `--no-keywords` | 不跑关键字 FOFA |
| `--validate` | 只测 FOFA 通不通 |

## 产出

xlsx 三张表：结果、分析、查询语句。默认写到 `out\`。

| 判定 | 含义 |
| --- | --- |
| 可疑钓鱼 | 第三方活体，同标题 / 像真站 |
| 可疑-被拦 | 像真站，被拦了 |
| 可疑-不通 | 测绘有，现在打不开 |
| 需人工 | 说不清 |
| 测绘过期 | 索引还在，站已经死 |
| 博彩/冒备案 | 博彩或假备案 |
| 自有 | 官网 |
| 排除 | 无关 |
| 未见注册 | 这个后缀没人注册 |

FOFA 返回 0 条只说明当前索引空。

## 目录

```text
启动.bat / run.cmd
ui.py
engine.py
config.example.json
assets/
tools/httpx.exe
tools/curl.exe
tools/lib/fofa_api.py
tools/lib/domain_icp.py
out/
```

公司名反查根域走 `https://icplishi.com/company/{公司全称}/`。

## 作者

**林神**

真正的大师永远怀着一颗学徒的心。

更新日志见 [CHANGELOG.md](CHANGELOG.md)。
