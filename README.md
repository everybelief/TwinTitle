<p align="center">
  <img src="assets/linshen.png" width="128" alt="TwinTitle">
</p>

<h1 align="center">TwinTitle</h1>

<p align="center">
  <b>同题猎手</b> · same-title phishing hunter<br>
  <i>by 林神</i>
</p>

<p align="center">
  Hunt phishing and lookalike sites that reuse a company's public title.
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">中文</a> · <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">
  <a href="https://github.com/everybelief/TwinTitle/releases/latest"><b>Download Windows exe</b></a>
</p>

<p align="center">
  <img src="assets/screenshot.png" alt="TwinTitle GUI">
</p>

---

## What it is

Give TwinTitle one or more **company legal names** (one per line). It:

1. Resolves official root domains from public ICP records
2. Probes the real homepage and fuzzes lookalike titles
3. Searches FOFA for exact / keyword titles
4. Live-probes every hit, checks ICP, mutates TLD aliases
5. Exports a scored xlsx: 结果 / 分析 / 查询语句

Chinese UI name: **同题猎手**. Repo / English name: **TwinTitle**.

## Pipeline

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

Root domains must be real ICP domains. Emails, `@`, `0.0.0.0`, public mailbox hosts are dropped.

## Features

- GUI (tkinter) + headless CLI
- One field is enough: company legal name
- Public ICP reverse lookup, no local ICP service to deploy
- FOFA official API (default interval 2s)
- Batch companies: results grouped by company → verdict
- Slogan rotates every 10s, no scroll
- Live probe ignores Clash TUN fake-ip `198.18.0.0/15`
- Drops news-center / mailbox templates whose title does not contain the company or keyword
- Keeps a single live official row as **自有**
- Bundled `httpx.exe` / `curl.exe` / FOFA / chinaz helpers

Not in scope: Hunter, Quake, WHOIS, ENScan, 爱企查.

## Requirements

- Windows
- Python 3.8+ with tkinter
- FOFA API key (`official` mode)

```text
pip install -r requirements.txt
```

`requirements.txt` currently: `openpyxl>=3.1.0`.

## Quick start

1. Copy config:

```text
copy config.example.json config.json
```

2. Put your FOFA key in `config.json` (or open the app → **配置**).
3. Or skip Python: grab `TwinTitle.exe` from [Releases](https://github.com/everybelief/TwinTitle/releases/latest), put FOFA key in **配置**.
4. Double-click `启动.bat` (or `run.cmd`) if you run from source.
5. Fill **公司名称** (legal name, one per line for batch). Single-company: roots / URL / keywords can stay empty. Batch mode ignores those two fields.
6. Click **开始排查**. Export xlsx when done.

Settings dialog also probes FOFA / proxy / ICP reverse so you know they work before a hunt.

## Config

`config.example.json`:

```json
{
  "fofa_key": "在这里填你的 FOFA API KEY",
  "fofa_mode": "official",
  "fofa_interval": 2,
  "proxy": "http://127.0.0.1:7897",
  "proxy_enable": false
}
```

| Field | Meaning |
| --- | --- |
| `fofa_key` | FOFA API key. Never commit `config.json`. |
| `fofa_mode` | `official` |
| `fofa_interval` | Seconds between FOFA calls (default 2) |
| `proxy` | Optional HTTP proxy |
| `proxy_enable` | Default `false`. FOFA / ICP reverse stay direct unless enabled. Live probe is always `--noproxy`. |

## CLI

```text
python engine.py --validate
python engine.py --title "某某集团有限公司" --out out/result.xlsx
python engine.py --title "甲公司有限公司,乙公司有限公司" --no-suffix --out out/batch.xlsx
```

| Flag | Meaning |
| --- | --- |
| `--title` | Company legal name (required; comma / newline for batch) |
| `--official` | Official roots, comma / newline |
| `--url` | Official URL |
| `--alias` | Alias roots |
| `--keywords` | Extra title keywords |
| `--out` | xlsx path |
| `--size` | FOFA page size (default 50) |
| `--no-roots` | Skip ICP reverse |
| `--no-probe` | Skip live probe |
| `--no-icp` | Skip chinaz ICP |
| `--no-suffix` | Skip TLD mutation |
| `--no-keywords` | Skip keyword FOFA |
| `--validate` | FOFA connectivity only |

## Output

xlsx, three sheets:

| Sheet | Content |
| --- | --- |
| 结果 | Company, verdict, URL, FOFA title, live title, IP, port, alive, ICP, org, query, note |
| 分析 | Hunt summary |
| 查询语句 | Each FOFA query + total / returned / error |

Default directory: `out\`.

### Verdicts

| Tag | Meaning |
| --- | --- |
| 可疑钓鱼 | Live third-party, same / lookalike title |
| 可疑-被拦 | Lookalike, WAF / 403 / challenge |
| 可疑-不通 | Lookalike in FOFA, dead now |
| 需人工 | Ambiguous, needs eyes |
| 测绘过期 | In FOFA index, not live |
| 博彩/冒备案 | Gambling / fake ICP |
| 自有 | Official live site |
| 排除 | Unrelated |
| 未见注册 | Alias TLD not registered |

A FOFA query that returns 0 hits only means the current index is empty. It does not prove the site does not exist.

## Layout

```text
TwinTitle/
  启动.bat / run.cmd     GUI entry
  ui.py                  GUI
  engine.py              Hunt engine + CLI
  config.example.json    Config template
  requirements.txt
  assets/linshen.ico     Brand icon (林神)
  assets/screenshot.png  GUI screenshot
  TwinTitle.spec         PyInstaller onefile
  tools/
    httpx.exe            Live probe (projectdiscovery 1.2.4)
    curl.exe             Pin FOFA IP when TUN poisons DNS
    lib/fofa_api.py
    lib/domain_icp.py    chinaz ICP (domain → license)
  out/                   Exports (gitignored)
```

## Notes

- Company → root uses `GET https://icplishi.com/company/{urlencoded name}/` only.
- If Clash TUN maps `icplishi.com` to `198.18.0.0/15`, the engine resolves real IPs over Ali/360 DoH and curls with `--http1.1 --resolve`.
- Live probe never goes through the proxy.
- Keep `config.json` and hunt results off git. See `.gitignore`.

## Author

**林神**

所谓的大佬，一辈子都以为自己是小白.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

### v1.1.0 — 2026-10-07

- Slogan swaps every 10s, no scroll
- Faster hunt: FOFA interval 2s, concurrent probe/ICP, suffix probe without FOFA
- Batch company names; results grouped by company → verdict

### v1.0.0 — 2026-10-06

- First public release of TwinTitle (同题猎手)
- Company legal name → public icplishi ICP reverse to official roots
- Probe official title, fuzz lookalike keywords
- FOFA exact `title=` + keyword search
- httpx live probe; Clash TUN fake-ip `198.18.0.0/15` retried with curl `--noproxy --resolve`
- chinaz ICP on lookalikes; TLD mutation for alias roots
- GUI: 林神 icon, scrolling slogans, by 林神, settings probe
- xlsx export: 结果 / 分析 / 查询语句
- `config.json` (FOFA key) is gitignored
