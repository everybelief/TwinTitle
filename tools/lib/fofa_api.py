#!/usr/bin/env python3
"""
FOFA API 调用模块
=====================================
支持两种模式（环境变量 FOFA_API_MODE 切换，默认 official）：
  - official: FOFA 官方 API (https://fofa.info)，适用于官方 VIP/高级会员 key，查询无限
  - relay:    第三方日卡代理 (fafaapi.info / hamal.cc.cd)，适用于日卡 key，200次/日
queryStr/qbase64 自动 Base64 编码，无需手动处理。

使用前先配置 KEY（二选一）：
  1. 环境变量: set FOFA_API_KEY=YOUR_FOFA_KEY
  2. Python 代码传参: FofaAPI(key="YOUR_FOFA_KEY")

依赖: Python 3.8+, urllib (标准库)
"""

import base64
import json
import os
import time
import urllib.parse
import urllib.request
import sys
from pathlib import Path
from datetime import datetime


# ============================================================
# 配置
# ============================================================

MODES = {
    # FOFA 官方 API（默认）
    "official": {
        "domains": ["https://fofa.info"],
        "paths": {
            "validate": "/api/v1/info/my",
            "search": "/api/v1/search/all",
            "stats": "/api/v1/search/stats",
            "host": "/api/v1/host/",
        },
    },
    # 第三方日卡代理（原配置）
    "relay": {
        "domains": ["https://fafaapi.info", "https://hamal.cc.cd"],
        "paths": {
            "validate": "/fofaapi/v1/validate-key",
            "search": "/fofaapi",
            "stats": "/fofaapi/stats",
            "host": "/fofaapi/host",
        },
    },
}

# 浏览器 UA（绕过 UA 检测的必要条件）
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 请求间隔（秒）— 服务器端约 3s 冷却，保守设为 3.5s
REQUEST_INTERVAL = 3.5

# 导出目录
EXPORT_DIR = Path.home() / "Desktop" / "fofa_export"


# ============================================================
# FOFA API 客户端
# ============================================================

class FofaAPI:
    """FOFA API 客户端（official / relay 双模式）"""

    def __init__(self, key=None, domain_index=0, route="5", request_interval=None, mode=None, proxy=None):
        """
        Args:
            key: API Key，默认从环境变量 FOFA_API_KEY 读取
            domain_index: 首选域名索引
            route: 线路（仅 relay 模式有效）
            request_interval: 请求间隔秒数
            mode: official（默认）| relay
            proxy: http 代理，如 http://127.0.0.1:7897；空则直连（不读环境变量）
        """
        self.key = key or os.environ.get("FOFA_API_KEY", "")
        if not self.key:
            raise ValueError("请设置 FOFA_API_KEY 环境变量或传入 key 参数")

        self.mode = (mode or os.environ.get("FOFA_API_MODE", "official")).lower()
        if self.mode not in MODES:
            raise ValueError(f"未知模式: {self.mode}（可选 official / relay）")

        self.domains = MODES[self.mode]["domains"]
        self.paths = MODES[self.mode]["paths"]
        self.domain_index = domain_index
        # 高级版 route 有效值 1-4（仅 relay 模式使用）
        self.route = str(route)
        self.request_interval = request_interval or REQUEST_INTERVAL
        self._last_request_time = 0
        self.proxy = (proxy or "").strip()

    @property
    def base_url(self):
        return self.domains[self.domain_index]

    def _encode_query(self, query: str) -> str:
        """FOFA 查询语句 → Base64"""
        return base64.b64encode(query.encode("utf-8")).decode()

    def _rate_limit(self):
        """速率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)

    def _request(self, path: str, params: dict) -> dict:
        """通用 HTTP GET 请求（带 UA + 自动容灾）"""
        for attempt in range(len(self.domains)):
            domain_idx = (self.domain_index + attempt) % len(self.domains)
            url = f"{self.domains[domain_idx]}{path}?{urllib.parse.urlencode(params)}"

            self._rate_limit()

            req = urllib.request.Request(url)
            req.add_header("User-Agent", BROWSER_UA)
            if self.proxy:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
                )
            else:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            try:
                with opener.open(req, timeout=30) as resp:
                    self._last_request_time = time.time()
                    data = json.loads(resp.read().decode("utf-8"))
                    # 切换域名后更新索引
                    if attempt > 0:
                        self.domain_index = domain_idx
                    return data
            except urllib.error.HTTPError as e:
                if e.code == 403 and attempt < len(self.domains) - 1:
                    continue  # 换域名重试
                # 尝试解析错误
                try:
                    err_data = json.loads(e.read().decode())
                    return err_data
                except Exception:
                    return {"error": True, "errmsg": f"HTTP {e.code}: {e.reason}"}
            except urllib.error.URLError as e:
                if attempt < len(self.domains) - 1:
                    continue  # 换域名重试
                return {"error": True, "errmsg": f"网络错误: {e.reason}"}
            except Exception as e:
                return {"error": True, "errmsg": str(e)}

        return {"error": True, "errmsg": "所有域名均不可用"}

    # ---- 开放接口 ----

    def validate(self) -> dict:
        """验证 Key 并获取配额信息"""
        if self.mode == "official":
            params = {
                "key": self.key,
                "fields": "username,email,isvip,vip_level,remain_api_query,remain_api_data,fcoin,fofa_point",
            }
        else:
            params = {"key": self.key}
        return self._request(self.paths["validate"], params)

    def search(
        self,
        query: str,
        fields: str = "ip,port,host,title,server,country,city",
        page: int = 1,
        size: int = 10,
        full: bool = False,
    ) -> dict:
        """
        资产搜索（核心接口）

        Args:
            query: FOFA 语法，如 'title="博客"'
            fields: 字段逗号分隔
            page: 页码
            size: 每页条数
            full: 全量数据开关
        Returns:
            official: {size, results: [[...]], fields, ...}
            relay:    {finalResults, total, newTodayRemaining, usedRoute, ...}
        """
        if self.mode == "official":
            params = {
                "key": self.key,
                "qbase64": self._encode_query(query),
                "fields": fields,
                "page": str(page),
                "size": str(size),
                "full": "true" if full else "false",
            }
        else:
            params = {
                "key": self.key,
                "queryStr": self._encode_query(query),
                "fields": fields,
                "page": str(page),
                "size": str(size),
                "full": "true" if full else "false",
                "route": self.route,
            }

        data = self._request(self.paths["search"], params)

        # official 模式：官方 API 不回显 fields 顺序，用请求时的字段名映射二维数组 → dict
        if self.mode == "official" and not data.get("error") and isinstance(data.get("results"), list):
            field_list = [f.strip() for f in fields.split(",") if f.strip()]
            data["finalResults"] = [
                {"fields": dict(zip(field_list, row))} for row in data["results"]
            ]

        return data

    def stats(
        self,
        query: str,
        fields: str = "port,server,protocol,country,os",
    ) -> dict:
        """
        统计聚合（统计端口/服务/协议/国家等分布）

        Args:
            query: FOFA 语法
            fields: 统计字段，逗号分隔
        Returns:
            official: {aggs: {field_name: {field_name: [{name, count}]}}, size, ...}
            relay:    {aggs: {field_name: [{name, count}]}, distinct, size, ...}
        """
        if self.mode == "official":
            params = {
                "key": self.key,
                "qbase64": self._encode_query(query),
                "fields": fields,
            }
        else:
            params = {
                "key": self.key,
                "q": self._encode_query(query),
                "fields": fields,
                "route": self.route,
            }
        return self._request(self.paths["stats"], params)

    def host(self, ip: str, detail: bool = True) -> dict:
        """
        IP 详情查询

        Args:
            ip: 目标 IP
            detail: 是否返回详细信息
        Returns:
            official: {host, ip, port, protocol, product, domain, os, server, ...}
            relay:    {host, port, protocol, ...}
        """
        if self.mode == "official":
            path = self.paths["host"] + urllib.parse.quote(ip)
            params = {"key": self.key, "detail": "true" if detail else "false"}
        else:
            path = self.paths["host"]
            params = {"key": self.key, "ip": ip, "detail": "true" if detail else "false"}
        return self._request(path, params)

    def switch_domain(self):
        """手动切换到备用域名"""
        self.domain_index = (self.domain_index + 1) % len(self.domains)
        return self.domain_index

    def set_route(self, route: str):
        """切换线路（仅 relay 模式有效）"""
        self.route = str(route)

    @staticmethod
    def _extract_rows(data: dict) -> list:
        """统一搜索结果 → list[dict{fields: {...}}]，兼容两种模式"""
        rows = data.get("finalResults")  # relay: list of dicts
        if rows is not None:
            return rows
        # official: results 是二维数组 + fields 顺序
        if isinstance(data.get("results"), list) and isinstance(data.get("fields"), list):
            field_list = data["fields"]
            return [{"fields": dict(zip(field_list, row))} for row in data["results"]]
        return []

    @staticmethod
    def format_results(data: dict) -> str:
        """格式化搜索结果成易读文本"""
        if data.get("error"):
            msg = data.get("errmsg") or data.get("message") or "未知错误"
            return f"❌ 错误: {msg}"

        rows = FofaAPI._extract_rows(data)
        total = data.get("total") or data.get("size") or 0
        remaining = data.get("newTodayRemaining")
        route = data.get("usedRoute")

        parts = [f"📊 总计 {total} 条 | 返回 {len(rows)} 条"]
        if remaining is not None:
            parts[0] += f" | 剩余配额: {remaining}"
        if route is not None:
            parts[0] += f" | 线路: {route}"

        lines = [parts[0], ""]

        for i, item in enumerate(rows, 1):
            fields = item.get("fields", item)
            line_parts = []
            for k, v in fields.items():
                v_str = str(v).strip() if v else "-"
                line_parts.append(f"{k}={v_str}")
            lines.append(f"  #{i}  {'  '.join(line_parts)}")

        return "\n".join(lines)


# ============================================================
# 工具函数（供 Skills 调用）
# ============================================================

def export_to_file(results: list, fields: str, filename: str = None) -> str:
    """
    搜索结果导出为 CSV 文件（桌面）
    Returns: 文件路径
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"fofa_export_{timestamp}.csv"

    filepath = EXPORT_DIR / filename

    field_list = [f.strip() for f in fields.split(",") if f.strip()]

    with open(filepath, "w", encoding="utf-8-sig") as f:
        f.write(",".join(field_list) + "\n")

        for item in results:
            fields_data = item.get("fields", item)
            row = []
            for field in field_list:
                val = str(fields_data.get(field, "") or "")
                # CSV escape
                if "," in val or '"' in val or "\n" in val:
                    val = '"' + val.replace('"', '""') + '"'
                row.append(val)
            f.write(",".join(row) + "\n")

    return str(filepath)


# ============================================================
# CLI 入口
# ============================================================

def print_usage():
    print("FOFA API 调用工具")
    print()
    print("用法:")
    print("  python fofa_api.py validate [--key xxx]                       # 验证 Key")
    print("  python fofa_api.py search <query> [fields] [options]          # 资产搜索")
    print("  python fofa_api.py stats <query> [fields]                     # 统计聚合")
    print("  python fofa_api.py host <ip>                                  # IP 详情")
    print()
    print("参数:")
    print("  --key xxx       API Key（也可用环境变量 FOFA_API_KEY）")
    print("  --size N        返回条数（搜索）")
    print("  --page N        页码（搜索）")
    print("  --full          全量数据（搜索）")
    print("  --export        导出 CSV（搜索）")
    print("  --route N       线路 1-5（仅 relay 模式）")
    print()
    print("环境变量:")
    print("  FOFA_API_KEY          API Key")
    print("  FOFA_API_MODE         模式: official(默认) | relay")
    print("  FOFA_DOMAIN_INDEX     首选域名索引（relay: 0=fafaapi.info, 1=hamal.cc.cd）")
    print("  FOFA_ROUTE            线路（1-5，仅 relay 模式）")
    print()
    print("示例:")
    print("  python fofa_api.py --key 86d71fae... validate")
    print("  python fofa_api.py search 'title=博客' ip,port,host --size 10")
    print("  python fofa_api.py search 'port=443 && country=CN' ip,port,host --export")
    print("  python fofa_api.py stats 'title=博客' port,server")
    print("  python fofa_api.py host 8.8.8.8")


def main():
    # Windows GBK 控制台编码兼容
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    # 解析 --key 参数（可以从任意位置提取）
    key_from_args = None
    filtered_args = []
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--key" and i + 1 < len(sys.argv):
            key_from_args = sys.argv[i + 1]
            i += 2
        else:
            filtered_args.append(sys.argv[i])
            i += 1

    if len(filtered_args) < 1:
        print_usage()
        sys.exit(1)

    command = filtered_args[0]

    try:
        # 初始化客户端（优先 --key > 环境变量）
        final_key = key_from_args or os.environ.get("FOFA_API_KEY", "")
        if not final_key:
            print("错误: 请通过 --key 参数或设置 FOFA_API_KEY 环境变量提供 API Key")
            sys.exit(1)

        domain_idx = int(os.environ.get("FOFA_DOMAIN_INDEX", "0"))
        route = os.environ.get("FOFA_ROUTE", "3")
        api = FofaAPI(key=final_key, domain_index=domain_idx, route=route)

        if command == "validate":
            result = api.validate()
            if api.mode == "official":
                if not result.get("error"):
                    print(f"✅ Key 有效（FOFA 官方 | 域名: {api.base_url}）")
                    for k in ("username", "email", "isvip", "vip_level",
                              "remain_api_query", "remain_api_data", "fcoin", "fofa_point"):
                        if k in result and result[k] is not None:
                            print(f"   {k}: {result[k]}")
                else:
                    print(f"❌ Key 无效: {result.get('message') or result.get('errmsg') or '未知'}")
            else:
                if result.get("valid"):
                    print(f"✅ Key 有效（relay 日卡）")
                    print(f"   首次使用: {result.get('firstUsedAt', '-')}")
                    print(f"   过期时间: {result.get('expireTime', '-')}")
                    print(f"   今日剩余: {result.get('todayRemaining', '-')}")
                    print(f"   总量剩余: {result.get('totalRemaining', '-')}")
                    print(f"   当前域名: {api.base_url}")
                    print(f"   当前线路: route={api.route}")
                else:
                    print(f"❌ Key 无效: {result.get('errmsg', '未知')}")

        elif command == "search":
            if len(filtered_args) < 2:
                print("错误: 请提供查询语句")
                sys.exit(1)
            query = filtered_args[1]
            fields = filtered_args[2] if len(filtered_args) > 2 else "ip,port,host,title,server,country,city"

            # 解析可选参数: --size N  --page N --full --export
            size = 10
            page = 1
            full = False
            do_export = False

            extra_args = filtered_args[3:] if len(filtered_args) > 3 else []
            i = 0
            while i < len(extra_args):
                if extra_args[i] == "--size" and i + 1 < len(extra_args):
                    size = int(extra_args[i + 1])
                    i += 2
                elif extra_args[i] == "--page" and i + 1 < len(extra_args):
                    page = int(extra_args[i + 1])
                    i += 2
                elif extra_args[i] == "--full":
                    full = True
                    i += 1
                elif extra_args[i] == "--export":
                    do_export = True
                    i += 1
                elif extra_args[i] == "--route" and i + 1 < len(extra_args):
                    api.set_route(extra_args[i + 1])
                    i += 2
                else:
                    i += 1

            result = api.search(query, fields, page=page, size=size, full=full)
            print(api.format_results(result))

            if do_export and not result.get("error"):
                results = FofaAPI._extract_rows(result)
                if results:
                    filepath = export_to_file(results, fields)
                    print(f"\n导出: {filepath}")

        elif command == "stats":
            if len(filtered_args) < 2:
                print("错误: 请提供查询语句")
                sys.exit(1)
            query = filtered_args[1]
            fields = filtered_args[2] if len(filtered_args) > 2 else "port,server,protocol,country,os"

            result = api.stats(query, fields)
            if result.get("error"):
                print(f"错误: {result.get('errmsg', '未知错误')}")
            else:
                print(f"统计结果 | 总计 {result.get('size', 0)} 条")
                print()
                aggs = result.get("aggs", {})
                for field_name, bucket in aggs.items():
                    # official 结构: {field: [{name, count}]} ; relay 结构: [{name, count}]
                    items = bucket
                    if isinstance(bucket, dict):
                        items = bucket.get(field_name, [])
                    if not isinstance(items, list):
                        continue
                    print(f"  [{field_name}]")
                    for item in items[:15]:
                        count = item.get("count", 0)
                        name = item.get("name", "-")
                        bar = "#" * min(count // 1000 + 1, 30)
                        print(f"    {name:20s} {count:>8,d}  {bar}")
                    if len(items) > 15:
                        print(f"    ... 还有 {len(items) - 15} 项")
                    print()

        elif command == "host":
            if len(filtered_args) < 2:
                print("错误: 请提供 IP 地址")
                sys.exit(1)
            ip_addr = filtered_args[1]
            result = api.host(ip_addr)
            if result.get("error"):
                print(f"❌ {result.get('errmsg', '未知错误')}")
            else:
                print(f"🔍 IP 详情: {ip_addr}")
                for k, v in result.items():
                    if k != "error" and not k.startswith("_"):
                        print(f"    {k}: {v}")

        else:
            print(f"❌ 未知命令: {command}")
            print_usage()
            sys.exit(1)

    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        print("提示: 设置环境变量 set FOFA_API_KEY=your_key")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
