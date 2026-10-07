# 更新日志

## v1.1.0 — 2026-10-07

- 顶栏标语一次只显示一条，10 秒整行换成下一条，不再滚动
- 排查加速：FOFA 默认间隔 2 秒；精确 title 额外标题只打 1 条；关键字 FOFA 最多 6 条；改后缀只探活不打 `host=`；httpx / curl / 备案并发
- 公司名称一行一个可批量；结果按「公司 → 可疑分类」分组，可疑默认展开、排除默认收起
- CLI `--title` 支持逗号 / 换行多公司，走 `run_batch`
- xlsx 结果表首列「公司」，判定仍按分类着色
- 启动不回填公司名 / 官网 URL / 根域；`config.json` 与 `last_config.json` 不进仓库

## v1.0.0 — 2026-10-06

TwinTitle（同题猎手）首发。

- 公司全称 → `icplishi.com/company/` 公开备案反查根域，不部署本机 ICP 服务
- 拼接 www / apex 探官网标题，fuzz 像真站关键字
- FOFA 官方 API：精确 `title=` + 关键字扩搜
- 探活主用随包 httpx；Clash TUN `198.18.0.0/15` 假 IP 不算存活，改走 curl `--noproxy --resolve`
- 像真站查 chinaz 备案
- 根名改 `.com` / `.net` / `.org` / `.top` / `.cn` / `.com.cn` 看是否注册及活体标题
- 丢掉标题不含公司名 / 关键字的资讯中心、邮箱模板；官网只留一条活体「自有」
- GUI：林神品牌图标、顶栏滚动标语、by 林神、右上角配置（FOFA / 代理 / 备案反查一键探测）
- 无头 CLI：`python engine.py --title ... --out result.xlsx`
- 导出 xlsx：结果 / 分析 / 查询语句
- `.gitignore` 排除 `config.json`、`last_config.json`、`out/`，FOFA Key 不进仓库
