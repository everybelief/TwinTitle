# 更新日志

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
