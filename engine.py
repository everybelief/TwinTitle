# -*- coding: utf-8 -*-
"""公司标题钓鱼排查引擎。按实战步骤：精确 title → 探活 → 备案 → 后缀/关键字扩搜。"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set
from urllib.parse import quote, urlparse

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    ROOT = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    ROOT = APP_DIR
TOOLS_DIR = ROOT / "tools"
LIB_DIR = TOOLS_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))
if not (LIB_DIR / "fofa_api.py").is_file():
    sys.path.insert(0, r"C:\Users\Administrator\.claude\skills\fofa-api")
if not (LIB_DIR / "domain_icp.py").is_file():
    sys.path.insert(0, r"C:\Users\Administrator\.grok\skills\domain-icp\tool")

from fofa_api import FofaAPI  # noqa: E402
import domain_icp  # noqa: E402

FOFA_FIELDS = "ip,port,host,title,server,protocol,link,icp,domain"
ICPLISHI = "https://icplishi.com"
ICP_LIC_RE = re.compile(
    r"(?:京|津|冀|晋|蒙|辽|吉|黑|沪|苏|浙|皖|闽|赣|鲁|豫|鄂|湘|粤|桂|琼|渝|川|蜀|贵|黔|云|滇|藏|陕|秦|甘|陇|青|宁|新)ICP[备证]\d+号(?:-\d+)?"
)
ICPLISHI_DOM_RE = re.compile(
    r'href="/([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)/"',
    re.I,
)


def _first_file(*cands: Path) -> str:
    for p in cands:
        if p and p.is_file():
            return str(p)
    return str(cands[0]) if cands else ""


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def load_runtime() -> dict:
    cfg: dict = {}
    cfg_path = APP_DIR / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    key = (os.environ.get("FOFA_API_KEY") or cfg.get("fofa_key") or "").strip()
    try:
        interval = float(cfg.get("fofa_interval") or 4)
    except (TypeError, ValueError):
        interval = 4.0
    return {
        "fofa_key": key,
        "fofa_mode": (cfg.get("fofa_mode") or os.environ.get("FOFA_API_MODE") or "official").strip() or "official",
        "fofa_interval": interval if interval >= 1 else 4.0,
        "httpx": _first_file(TOOLS_DIR / "httpx.exe", Path(r"F:\cheshi\03_Fingerprinting\httpx.exe")),
        "curl": _first_file(TOOLS_DIR / "curl.exe", Path(r"C:\Windows\System32\curl.exe")),
        "proxy": (cfg.get("proxy") or "http://127.0.0.1:7897").strip(),
        "proxy_enable": _as_bool(cfg.get("proxy_enable"), False),
        "fofa_lib": str(LIB_DIR / "fofa_api.py"),
        "icp_lib": str(LIB_DIR / "domain_icp.py"),
        "config": str(cfg_path),
    }


def save_runtime(updates: dict) -> dict:
    path = APP_DIR / "config.json"
    cfg: dict = {}
    if path.is_file():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    for key, value in (updates or {}).items():
        if key in ("httpx", "curl", "fofa_lib", "icp_lib", "config", "icp_query"):
            continue
        cfg[key] = value
    cfg.pop("icp_query", None)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return load_runtime()


def probe_settings(
    fofa_key: str = "",
    fofa_mode: str = "official",
    proxy: str = "",
    proxy_enable: bool = False,
    log: Optional[LogFn] = None,
) -> List[dict]:
    """探测 FOFA Key / 代理 / 公开备案反查。不打印 Key。"""
    say = log or (lambda m: None)
    rt = load_runtime()
    curl = rt.get("curl") or ""
    rows: List[dict] = []

    key = (fofa_key or "").strip()
    mode = (fofa_mode or "official").strip() or "official"
    proxy = (proxy or "").strip()
    fofa_proxy = proxy if proxy_enable and proxy else ""

    if not key:
        rows.append({"name": "FOFA", "ok": False, "status": "无效", "detail": "未填 Key"})
    else:
        say("[探测] FOFA validate%s" % (" 走代理" if fofa_proxy else " 直连"))
        try:
            api = FofaAPI(key=key, mode=mode, request_interval=1.0, proxy=fofa_proxy or None)
            info = api.validate() or {}
            if info.get("error"):
                rows.append({
                    "name": "FOFA", "ok": False, "status": "无效",
                    "detail": str(info.get("errmsg") or info.get("message") or info)[:160],
                })
            else:
                remain = info.get("remain_api_query")
                vip = info.get("isvip")
                user = info.get("username") or info.get("email") or ""
                if "@" in str(user):
                    user = str(user).split("@", 1)[0]
                detail = "VIP=%s 剩余查询=%s" % (vip, remain)
                if user:
                    detail = "%s  %s" % (user, detail)
                rows.append({"name": "FOFA", "ok": True, "status": "可用", "detail": detail})
        except Exception as exc:
            rows.append({"name": "FOFA", "ok": False, "status": "无效", "detail": str(exc)[:160]})

    if not proxy:
        rows.append({"name": "代理", "ok": False, "status": "无效", "detail": "未填代理地址"})
    elif not Path(curl).is_file():
        rows.append({"name": "代理", "ok": False, "status": "未知", "detail": "没有 curl，测不了代理"})
    else:
        say("[探测] 代理 %s" % proxy)
        body = tempfile.NamedTemporaryFile(prefix="phish_proxy_", suffix=".txt", delete=False)
        body.close()
        cmd = [
            curl, "-sS", "-m", "8", "-x", proxy,
            "-A", "Mozilla/5.0",
            "-o", body.name, "-w", "%{http_code}",
            "http://www.baidu.com/",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            code = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            if proc.returncode == 0 and code.startswith("2"):
                note = "启用中，FOFA 将走代理" if proxy_enable else "连通，当前未启用（国内测绘建议直连）"
                rows.append({"name": "代理", "ok": True, "status": "可用", "detail": "HTTP %s  %s" % (code, note)})
            else:
                rows.append({
                    "name": "代理", "ok": False, "status": "无效",
                    "detail": ("HTTP %s " % code if code else "") + (err[:120] or "连不上"),
                })
        except Exception as exc:
            rows.append({"name": "代理", "ok": False, "status": "无效", "detail": str(exc)[:160]})
        finally:
            try:
                os.unlink(body.name)
            except OSError:
                pass

    say("[探测] 备案反查 %s/company/" % ICPLISHI)
    if icplishi_alive(timeout=6):
        rows.append({
            "name": "备案反查", "ok": True, "status": "可用",
            "detail": "%s/company/ 公开接口，别人不用部署" % ICPLISHI,
        })
    else:
        rows.append({
            "name": "备案反查", "ok": False, "status": "无效",
            "detail": "icplishi.com 连不上",
        })
    return rows


def tool_inventory() -> List[dict]:
    rt = load_runtime()

    def row(name: str, role: str, ver: str, path: str, ok: Optional[bool] = None) -> dict:
        exists = Path(path).is_file() if path else False
        ready = exists if ok is None else ok
        return {
            "name": name,
            "role": role,
            "ver": ver,
            "path": path,
            "ok": ready,
            "status": "就绪" if ready else "缺失",
        }

    rows = [
        row("httpx", "批量探活（标题/状态码/CDN）", "projectdiscovery 1.2.4", rt["httpx"]),
        row("curl", "钉测绘 IP 探活（Clash 回退）", "Windows curl", rt["curl"]),
        row("FOFA API", "测绘检索 title / host", "official VIP", rt["fofa_lib"]),
        row("备案查询", "chinaz 备案号与主体", "domain_icp", rt["icp_lib"]),
        row("备案反查", "公司名→备案根域（公开）", "icplishi.com", ICPLISHI, ok=True),
        row("FOFA Key", "config.json 或环境变量", "official", rt["config"], ok=bool(rt["fofa_key"])),
    ]
    try:
        import openpyxl  # noqa: F401
        ox_ok, ox_path = True, getattr(sys.modules["openpyxl"], "__file__", "openpyxl")
    except Exception:
        ox_ok, ox_path = False, "pip install -r requirements.txt"
    rows.append(row("openpyxl", "导出分析结果 xlsx", "pip", ox_path, ok=ox_ok))
    try:
        import tkinter  # noqa: F401
        tk_ok, tk_path = True, "tkinter"
    except Exception:
        tk_ok, tk_path = False, "需要带 Tcl/Tk 的 Python"
    rows.append(row("tkinter", "图形界面", "stdlib", tk_path, ok=tk_ok))
    return rows

SECOND_LEVEL = {"com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn", "co.uk"}
MAIL_ROOTS = {
    "163.com", "126.com", "yeah.net", "188.com", "vip.163.com",
    "qq.com", "vip.qq.com", "foxmail.com",
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "sina.com", "sina.cn", "vip.sina.com", "sohu.com",
    "139.com", "189.cn", "aliyun.com", "21cn.com", "tom.com",
    "icloud.com", "me.com", "yahoo.com", "yahoo.com.cn", "ymail.com",
}
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
GAMBLE_RE = re.compile(
    r"金沙|威尼斯人|百家乐|bwin|开元棋牌|蘑菇视频|体育投注|彩票|网赌|电子游艺|AG亚游",
    re.I,
)
JUNK_TITLE_RE = re.compile(
    r"资讯中心|免费邮箱|企业邮箱|网易邮箱|网易免费|加速器下载|UU加速|Protected data",
    re.I,
)
GENERIC_LIVE_RE = re.compile(
    r"网易|\bnginx\b|openresty|index of|attention required|just a moment",
    re.I,
)
TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")

LogFn = Callable[[str], None]


@dataclass
class HuntConfig:
    title: str
    official_domains: List[str] = field(default_factory=list)
    official_url: str = ""
    alias_domains: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    do_roots: bool = True
    do_exact: bool = True
    do_probe: bool = True
    do_icp: bool = True
    do_suffix: bool = True
    do_keywords: bool = True
    size: int = 50
    probe_timeout: int = 12
    max_probe: int = 80


@dataclass
class Hit:
    query: str
    ip: str = ""
    port: str = ""
    host: str = ""
    fofa_title: str = ""
    live_title: str = ""
    url: str = ""
    protocol: str = ""
    domain: str = ""
    icp: str = ""
    icp_org: str = ""
    alive: str = ""
    verdict: str = ""
    note: str = ""
    own: bool = False


def _norm_host(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return ""
    if "@" in text and "://" not in text:
        return ""
    text = text.replace("https://", "").replace("http://", "")
    if "@" in text:
        return ""
    text = text.split("/")[0].split("?")[0].split("#")[0]
    if text.startswith("[") and "]" in text:
        text = text[1:text.index("]")]
    if ":" in text and not _is_ip(text.split(":")[0]):
        host, _, port = text.rpartition(":")
        if port.isdigit():
            text = host
    return text.strip(".")


def is_valid_root(raw: str) -> bool:
    """根域只能是备案域名，邮箱 / IP / 0.0.0.0 / 公共邮箱商一律丢掉。"""
    text = (raw or "").strip().lower()
    if not text or "@" in text or " " in text:
        return False
    host = _norm_host(text)
    if not host or "@" in host or _is_ip(host):
        return False
    if host in ("localhost", "local", "invalid"):
        return False
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return False
    for part in parts:
        if not LABEL_RE.match(part):
            return False
    root = root_domain(host)
    if not root or _is_ip(root) or root in MAIL_ROOTS:
        return False
    return True


def is_valid_http_url(url: str) -> bool:
    text = (url or "").strip()
    if not text or "@" in text:
        return False
    parsed = urlparse(text if "://" in text else "http://" + text)
    if parsed.username or parsed.password:
        return False
    return is_valid_root(parsed.hostname or "")


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def _is_fake_ip(text: str) -> bool:
    try:
        return ipaddress.ip_address((text or "").split("%")[0].strip()) in FAKE_IP_NET
    except ValueError:
        return False


def _usable_ip(text: str) -> str:
    ip = (text or "").strip()
    if not ip or ip in ("0.0.0.0", "::") or _is_fake_ip(ip):
        return ""
    if not _is_ip(ip):
        return ""
    return ip


def _title_has_needles(title: str, needles: Iterable[str]) -> bool:
    blob = title or ""
    for kw in needles:
        kw = (kw or "").strip()
        if kw and len(kw) >= 4 and kw in blob:
            return True
    return False


def _is_junk_title(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return False
    return bool(JUNK_TITLE_RE.search(text))


def _noproxy_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _curl_bin() -> str:
    return _first_file(TOOLS_DIR / "curl.exe", Path(r"C:\Windows\System32\curl.exe"))


def _curl_http(url: str, timeout: float, resolve_host: str = "", resolve_ip: str = "") -> tuple:
    curl = _curl_bin()
    if not Path(curl).is_file():
        return "", "", "没有 curl"
    bodyf = tempfile.NamedTemporaryFile(prefix="icplishi_", suffix=".html", delete=False)
    bodyf.close()
    cmd = [
        curl, "--noproxy", "*", "--http1.1", "-sS", "-L",
        "-m", str(max(8, int(timeout))),
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "-e", ICPLISHI + "/",
        "-o", bodyf.name, "-w", "%{http_code}",
    ]
    if resolve_host and resolve_ip:
        cmd.extend(["--resolve", "%s:443:%s" % (resolve_host, resolve_ip)])
        cmd.extend(["--resolve", "%s:80:%s" % (resolve_host, resolve_ip)])
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        code = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        raw = ""
        if Path(bodyf.name).is_file():
            raw = Path(bodyf.name).read_text(encoding="utf-8", errors="replace")
        return code, raw, err
    except Exception as exc:
        return "", "", str(exc)
    finally:
        try:
            os.unlink(bodyf.name)
        except OSError:
            pass


def _doh_a(host: str) -> List[str]:
    """阿里/360 DoH 拿 A 记录。绕开 Clash fake-ip。"""
    curl = _curl_bin()
    if not host or not Path(curl).is_file():
        return []
    urls = [
        "https://dns.alidns.com/resolve?name=%s&type=A" % host,
        "https://doh.360.cn/query?name=%s&type=A" % host,
    ]
    ips: List[str] = []
    for url in urls:
        cmd = [curl, "--noproxy", "*", "-sS", "-m", "8", "-A", "Mozilla/5.0", url]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            data = json.loads(proc.stdout or "")
        except Exception:
            continue
        for ans in data.get("Answer") or []:
            try:
                typ = int(ans.get("type") or 0)
            except (TypeError, ValueError):
                typ = 0
            if typ != 1:
                continue
            ip = _usable_ip((ans.get("data") or "").strip())
            if ip and ip not in ips:
                ips.append(ip)
        if ips:
            return ips
    return ips


def _system_ips(host: str) -> List[str]:
    import socket
    out: List[str] = []
    try:
        for item in socket.getaddrinfo(host, 443, socket.AF_INET):
            ip = _usable_ip(item[4][0] if item and item[4] else "")
            if ip and ip not in out:
                out.append(ip)
    except Exception:
        pass
    return out


def _system_raw_ips(host: str) -> List[str]:
    import socket
    out: List[str] = []
    try:
        for item in socket.getaddrinfo(host, 443, socket.AF_INET):
            ip = (item[4][0] if item and item[4] else "").strip()
            if ip and ip not in out:
                out.append(ip)
    except Exception:
        pass
    return out


def _real_ips(host: str) -> List[str]:
    ips = _system_ips(host)
    if ips:
        return ips
    return _doh_a(host)


def icplishi_alive(timeout: float = 8.0) -> bool:
    host = "icplishi.com"
    ips = _real_ips(host) or [""]
    for ip in ips[:4]:
        code, raw, _err = _curl_http(ICPLISHI + "/", timeout, host, ip)
        if code.startswith("2") and (raw or code):
            return True
    return False


def parse_icplishi_company(html: str, company: str) -> List[dict]:
    """从 icplishi 公司页表格抽出 备案号+域名。丢掉侧栏「最新查询」。"""
    if not html or "该页面无法显示" in html or ">404错误<" in html:
        return []
    head = html.split("最新ICP备案查询", 1)[0]
    rows: List[dict] = []
    seen: Set[str] = set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", head, re.I | re.S):
        lic_m = ICP_LIC_RE.search(tr)
        for raw in ICPLISHI_DOM_RE.findall(tr):
            host = (raw or "").strip().lower()
            if not host or "icp" in host or host in seen:
                continue
            seen.add(host)
            rows.append({
                "domain": host,
                "serviceLicence": lic_m.group(0) if lic_m else "",
                "unitName": company,
            })
    return rows


def fetch_icplishi_company(company: str, timeout: float = 45.0, log: Optional[Callable] = None) -> List[dict]:
    name = (company or "").strip()
    if not name:
        return []
    say = log or (lambda m: None)
    host = "icplishi.com"
    url = "%s/company/%s/" % (ICPLISHI, quote(name, safe=""))
    raw_dns = _system_raw_ips(host)
    fake = [ip for ip in raw_dns if _is_fake_ip(ip)]
    ips = _real_ips(host)
    if fake and ips:
        say("[根域] Clash 假IP %s，改网宿 %s" % ("、".join(fake), "、".join(ips[:3])))
    elif fake and not ips:
        say("[根域] Clash 假IP %s，DoH 也没拿到真 IP" % "、".join(fake))
        return []
    elif not ips:
        say("[根域] 解析不到 icplishi.com")
        return []
    last_err = ""
    for ip in ips[:4]:
        say("[根域] GET %s  --resolve %s" % (url, ip))
        code, raw, err = _curl_http(url, timeout, host, ip)
        if not (code or "").startswith("2") or not raw:
            last_err = "HTTP %s %s %s" % (code or "空", ip, (err or "空回复")[:80])
            say("[根域] %s" % last_err)
            continue
        rows = parse_icplishi_company(raw, name)
        say("[根域] HTTP %s  %s 字节  %s 条" % (code, len(raw), len(rows)))
        if rows:
            return rows
        last_err = "HTTP %s 有页无域名" % code
    if last_err:
        say("[根域] icplishi 失败 %s" % last_err)
    return []


def root_domain(host: str) -> str:
    host = _norm_host(host)
    if not host:
        return ""
    if _is_ip(host):
        return host
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in SECOND_LEVEL:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def split_list(text: str) -> List[str]:
    out: List[str] = []
    for line in (text or "").replace("，", ",").replace(";", "\n").replace(",", "\n").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if item not in out:
            out.append(item)
    return out


LEGAL_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|集团公司|集团有限公司|集团|控股|分公司|门户网站|官方网站|网站|首页|-首页|－首页)"
)
GENERIC_KW = {"集团", "公司", "网站", "首页", "官方", "门户", "有限", "股份"}
INDUSTRY_EXPAND = (
    ("轨道交通", ["地铁", "城轨"]),
    ("地铁", ["城轨", "轨道交通"]),
)


def fuzz_titles(company: str, extra: Iterable[str] = ()) -> List[str]:
    """用公司全称和官网标题生成像真站关键字。"""
    seeds: List[str] = []
    for raw in [company, *list(extra)]:
        text = WS_RE.sub(" ", (raw or "")).strip()
        if text and text not in seeds:
            seeds.append(text)
    out: List[str] = []

    def add(text: str) -> None:
        text = WS_RE.sub(" ", (text or "")).strip(" -_|/\\")
        if len(text) < 4 or len(text) > 24:
            return
        if text == (company or "").strip():
            return
        if GENERIC_LIVE_RE.search(text) or JUNK_TITLE_RE.search(text):
            return
        industry_only = {k for k, _ in INDUSTRY_EXPAND}
        industry_only.update(a for _, alts in INDUSTRY_EXPAND for a in alts)
        if text in GENERIC_KW or text in industry_only or text in out:
            return
        out.append(text)

    for seed in seeds:
        stripped = LEGAL_RE.sub("", seed).strip()
        add(stripped)
        for key, alts in INDUSTRY_EXPAND:
            if key not in stripped:
                continue
            for alt in alts:
                add(stripped.replace(key, alt))
    return out[:12]


def official_candidate_urls(domains: Iterable[str], extra_urls: Iterable[str] = ()) -> List[str]:
    out: List[str] = []
    for u in extra_urls:
        u = (u or "").strip()
        if u and is_valid_http_url(u) and u not in out:
            out.append(u)
    for d in domains:
        if not is_valid_root(d):
            continue
        root = root_domain(d)
        if not root or _is_ip(root):
            continue
        for host in ("www." + root, root):
            for scheme in ("https", "http"):
                url = "%s://%s/" % (scheme, host)
                if url not in out:
                    out.append(url)
    return out


def suffix_variants(domains: Iterable[str]) -> List[str]:
    tlds = (".com", ".net", ".org", ".top", ".cn", ".com.cn")
    out: List[str] = []
    for d in domains:
        if not is_valid_root(d):
            continue
        root = root_domain(d)
        if not root or _is_ip(root):
            continue
        name = root.split(".")[0]
        if not name or "@" in name:
            continue
        for tld in tlds:
            cand = name + tld
            if cand != root and cand not in out:
                out.append(cand)
    return out


def build_url(host: str, port: str, protocol: str) -> str:
    host = (host or "").strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host
    proto = (protocol or "").lower()
    try:
        p = int(str(port or "0"))
    except ValueError:
        p = 0
    if proto in ("https", "http"):
        scheme = proto
    elif p in (443, 8443, 9443, 7443, 10443, 15001, 18888, 1443):
        scheme = "https"
    else:
        scheme = "http"
    if ":" in host and not host.startswith("["):
        # already host:port from FOFA
        if scheme == "https":
            return "https://" + host
        return "http://" + host
    if p and p not in (80, 443):
        return "%s://%s:%s/" % (scheme, host, p)
    return "%s://%s/" % (scheme, host)


def fofa_escape_title(title: str) -> str:
    return (title or "").replace("\\", "\\\\").replace('"', '\\"')


class TitlePhishEngine:
    def __init__(self, log: Optional[LogFn] = None, interval: Optional[float] = None):
        self.log = log or (lambda m: None)
        rt = load_runtime()
        self.httpx = rt["httpx"]
        self.curl = rt["curl"]
        self.fofa_key = rt["fofa_key"]
        if interval is None:
            try:
                interval = float(rt.get("fofa_interval") or 4)
            except (TypeError, ValueError):
                interval = 4.0
        if not self.fofa_key:
            raise ValueError("未配置 FOFA Key。点右上角「配置」填写。")
        os.environ["FOFA_API_KEY"] = self.fofa_key
        os.environ["FOFA_API_MODE"] = rt["fofa_mode"]
        proxy = (rt.get("proxy") or "").strip() if rt.get("proxy_enable") else ""
        self.proxy = proxy
        self.api = FofaAPI(
            key=self.fofa_key,
            mode=rt["fofa_mode"],
            request_interval=interval,
            proxy=proxy or None,
        )
        self._icp_cache: Dict[str, tuple] = {}
        self._ip_cache: Dict[str, str] = {}
        self._stop = False
        self._proc: Optional[subprocess.Popen] = None

    def stop(self) -> None:
        self._stop = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _say(self, msg: str) -> None:
        self.log(msg)

    def search(self, query: str, size: int = 50) -> dict:
        last_err = None
        for attempt in range(3):
            if self._stop:
                return {"error": True, "errmsg": "stopped", "finalResults": [], "total": 0}
            try:
                data = self.api.search(query, fields=FOFA_FIELDS, size=size)
            except Exception as exc:
                last_err = str(exc)
                self._say("[FOFA] 异常 %s" % exc)
                time.sleep(6)
                continue
            if data.get("error"):
                last_err = data.get("errmsg") or data.get("message") or str(data)
                self._say("[FOFA] 错误 %s" % last_err)
                if "频繁" in str(last_err) or "45012" in str(last_err):
                    time.sleep(8)
                    continue
                break
            total = data.get("total")
            if total is None:
                total = data.get("size")
            rows = data.get("finalResults") or []
            self._say("[FOFA] total=%s n=%s  %s" % (total, len(rows), query))
            data["total"] = total
            return data
        return {"error": True, "errmsg": last_err, "finalResults": [], "total": 0}

    def _fofa_ip(self, host: str) -> str:
        host = _norm_host(host)
        if not host or _is_ip(host) or not is_valid_root(host):
            return ""
        if host in self._ip_cache:
            return self._ip_cache[host]
        ip = ""
        data = self.search('host="%s"' % host, 20)
        for f in self._rows(data):
            cand = _usable_ip(str(f.get("ip") or ""))
            if cand:
                ip = cand
                break
        self._ip_cache[host] = ip
        if ip:
            self._say("[测绘IP] %s -> %s" % (host, ip))
        return ip

    def icp(self, domain: str) -> tuple:
        root = root_domain(domain)
        if not root or _is_ip(root) or not is_valid_root(root):
            return "", ""
        if root in self._icp_cache:
            return self._icp_cache[root]
        try:
            name = domain_icp.clean_domain(root)
            code, html = domain_icp.fetch(name, 20)
            if code >= 400:
                rec = ("查询失败 HTTP %s" % code, "")
            else:
                license_no, company = domain_icp.parse(html)
                rec = (license_no or "未收录", company or "")
        except Exception as exc:
            rec = ("查询失败", str(exc))
        self._icp_cache[root] = rec
        return rec

    def probe(self, url: str, host: str, ip: str, port: str, timeout: int) -> dict:
        out = {"alive": "不通", "live_title": "", "status": "", "note": ""}
        if not url:
            return out
        parsed = urlparse(url if "://" in url else "http://" + url)
        hostname = parsed.hostname or _norm_host(host)
        try:
            p = int(parsed.port or port or (443 if parsed.scheme == "https" else 80))
        except ValueError:
            p = 443 if parsed.scheme == "https" else 80
        hdr = tempfile.NamedTemporaryFile(prefix="phish_hdr_", suffix=".txt", delete=False)
        body = tempfile.NamedTemporaryFile(prefix="phish_body_", suffix=".html", delete=False)
        hdr.close()
        body.close()
        cmd = [
            self.curl, "--noproxy", "*", "-k", "-sS", "-L",
            "--max-time", str(timeout),
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "-D", hdr.name, "-o", body.name,
        ]
        if ip and hostname and not _is_ip(hostname):
            cmd += ["--resolve", "%s:%s:%s" % (hostname, p, ip)]
        cmd.append(url)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            err = (proc.stderr or "").strip()
            headers = Path(hdr.name).read_text(encoding="utf-8", errors="replace")
            html = Path(body.name).read_bytes()
            status = ""
            for line in headers.splitlines():
                if line.upper().startswith("HTTP/"):
                    parts = line.split()
                    if len(parts) >= 2:
                        status = parts[1]
            title = ""
            try:
                text = html.decode("utf-8")
            except UnicodeDecodeError:
                text = html.decode("gb18030", errors="replace")
            m = TITLE_RE.search(text)
            if m:
                title = WS_RE.sub(" ", TAG_RE.sub("", m.group(1))).strip()
            if "schannel" in err or "SSL" in err or "TLS" in err:
                out = {"alive": "TLS失败", "live_title": title, "status": status, "note": err[:180]}
            elif "Empty reply" in err:
                out = {"alive": "空回复", "live_title": title, "status": status, "note": "curl 52"}
            elif "timed out" in err.lower() or "timeout" in err.lower():
                out = {"alive": "超时", "live_title": title, "status": status, "note": err[:180]}
            elif proc.returncode != 0 and not status:
                out = {"alive": "不通", "live_title": title, "status": status, "note": err[:180]}
            elif status == "403":
                if "cloudflare" in (title + headers).lower():
                    out = {"alive": "被拦 403 Cloudflare", "live_title": title or "Attention Required! | Cloudflare", "status": status, "note": ""}
                else:
                    out = {"alive": "403", "live_title": title, "status": status, "note": ""}
            elif status == "502":
                out = {"alive": "502", "live_title": title, "status": status, "note": ""}
            elif status.startswith("3") or status.startswith("2") or status == "404":
                label = "通 %s" % status
                out = {"alive": label, "live_title": title, "status": status, "note": ""}
            else:
                out = {"alive": status or "不通", "live_title": title, "status": status, "note": err[:180]}
        except Exception as exc:
            out = {"alive": "不通", "live_title": "", "status": "", "note": str(exc)}
        finally:
            for pth in (hdr.name, body.name):
                try:
                    os.unlink(pth)
                except OSError:
                    pass
        return out

    def _httpx_env(self) -> dict:
        env = os.environ.copy()
        for key in list(env):
            if key.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY"):
                env.pop(key, None)
        env["NO_PROXY"] = "*"
        env["no_proxy"] = "*"
        return env

    def _httpx_to_probe(self, obj: dict) -> dict:
        failed = obj.get("failed")
        status = obj.get("status-code")
        status = "" if status is None else str(status)
        title = (obj.get("title") or "").strip()
        web = obj.get("webserver") or ""
        cdn = obj.get("cdn")
        ip = str(obj.get("host") or obj.get("ip") or "")
        notes = []
        if web:
            notes.append(str(web))
        if cdn:
            notes.append("CDN %s" % cdn)
        if _is_fake_ip(ip):
            notes.append("Clash fake-ip")
        note = " | ".join(notes)
        if _is_fake_ip(ip):
            return {
                "alive": "Clash污染", "live_title": title, "status": status,
                "note": note, "resolved_ip": ip,
            }
        if failed:
            return {
                "alive": "不通", "live_title": title, "status": status,
                "note": note or "httpx failed", "resolved_ip": ip,
            }
        if status == "403":
            blob = (title + " " + web + " " + str(cdn)).lower()
            if "cloudflare" in blob:
                return {
                    "alive": "被拦 403 Cloudflare",
                    "live_title": title or "Attention Required! | Cloudflare",
                    "status": status, "note": note, "resolved_ip": ip,
                }
            return {"alive": "403", "live_title": title, "status": status, "note": note, "resolved_ip": ip}
        if status == "502":
            return {"alive": "502", "live_title": title, "status": status, "note": note, "resolved_ip": ip}
        if status.startswith("2") or status.startswith("3") or status == "404":
            return {"alive": "通 %s" % status, "live_title": title, "status": status, "note": note, "resolved_ip": ip}
        if status:
            return {"alive": status, "live_title": title, "status": status, "note": note, "resolved_ip": ip}
        return {
            "alive": "不通", "live_title": title, "status": status,
            "note": note or "httpx 无状态码", "resolved_ip": ip,
        }

    def _need_curl_fallback(self, pr: dict, job: dict) -> bool:
        alive = pr.get("alive") or ""
        note = pr.get("note") or ""
        resolved = pr.get("resolved_ip") or ""
        if alive == "Clash污染" or "Clash fake-ip" in note or _is_fake_ip(resolved) or _is_fake_ip(job.get("ip") or ""):
            return True
        if not _usable_ip(job.get("ip") or ""):
            return alive in ("不通", "超时", "空回复", "TLS失败", "502", "Clash污染") or alive.startswith("不通")
        return alive in ("不通", "超时", "空回复", "TLS失败", "502", "Clash污染") or alive.startswith("不通")

    def _lookup_probe(self, bag: Dict[str, dict], url: str) -> Optional[dict]:
        if url in bag:
            return bag[url]
        if url.endswith("/") and url.rstrip("/") in bag:
            return bag[url.rstrip("/")]
        if not url.endswith("/") and (url + "/") in bag:
            return bag[url + "/"]
        return None

    def probe_batch(self, jobs: List[dict], timeout: int, threads: int = 20) -> Dict[str, dict]:
        """httpx 并发探活。Clash 打不开且有测绘 IP 时再 curl --resolve。"""
        out: Dict[str, dict] = {}
        by_url: Dict[str, dict] = {}
        urls: List[str] = []
        for job in jobs:
            url = (job.get("url") or "").strip()
            if not url or url in by_url:
                continue
            by_url[url] = job
            urls.append(url)
        if not urls:
            return out

        def curl_all() -> Dict[str, dict]:
            got: Dict[str, dict] = {}
            for url, job in by_url.items():
                if self._stop:
                    break
                self._say("[探活] curl %s" % url)
                got[url] = self.probe(url, job.get("host") or "", job.get("ip") or "", job.get("port") or "", timeout)
            return got

        if not Path(self.httpx).is_file():
            self._say("[探活] 找不到 httpx，改 curl")
            return curl_all()

        workdir = tempfile.mkdtemp(prefix="phish_httpx_")
        list_path = str(Path(workdir) / "urls.txt")
        Path(list_path).write_text("\n".join(urls) + "\n", encoding="utf-8")
        nthread = max(5, min(50, int(threads), len(urls)))
        cmd = [
            self.httpx, "-l", list_path,
            "-title", "-status-code", "-ip", "-web-server", "-cdn",
            "-json", "-silent", "-follow-redirects",
            "-timeout", str(max(5, int(timeout))),
            "-threads", str(nthread),
            "-no-color", "-no-fallback-scheme", "-probe",
        ]
        self._say("[探活] httpx 批量 %s 条 threads=%s" % (len(urls), nthread))
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._httpx_env(),
                cwd=workdir,
            )
            try:
                stdout, stderr = self._proc.communicate(timeout=max(60, int(timeout) * 4 + 20))
            except subprocess.TimeoutExpired:
                self._proc.kill()
                stdout, stderr = self._proc.communicate()
                self._say("[探活] httpx 超时，已杀进程")
            if stderr:
                for line in stderr.splitlines():
                    text = line.strip()
                    if text and "Current Version" not in text and "projectdiscovery" not in text.lower():
                        self._say("[httpx] %s" % text[:200])
            for line in (stdout or "").splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (obj.get("input") or obj.get("url") or "").strip()
                if not key:
                    continue
                out[key] = self._httpx_to_probe(obj)
        except Exception as exc:
            self._say("[探活] httpx 失败 %s，改 curl" % exc)
            return curl_all()
        finally:
            self._proc = None
            shutil.rmtree(workdir, ignore_errors=True)

        for url, job in by_url.items():
            if self._stop:
                break
            pr = self._lookup_probe(out, url)
            if pr and not self._need_curl_fallback(pr, job):
                out[url] = pr
                continue
            host = job.get("host") or ""
            ip = _usable_ip(job.get("ip") or "") or _usable_ip((pr or {}).get("resolved_ip") or "")
            if not ip:
                ip = self._fofa_ip(host)
            if ip:
                self._say("[探活] httpx 未中/Clash，curl --resolve %s -> %s" % (url, ip))
            else:
                self._say("[探活] httpx 未中，curl --noproxy %s" % url)
            got = self.probe(url, host, ip, job.get("port") or "", timeout)
            if ip and _is_fake_ip(got.get("resolved_ip") or ""):
                got["alive"] = "Clash污染"
                got["note"] = ((got.get("note") or "") + " | Clash fake-ip").strip(" |")
            elif (got.get("alive") or "").startswith("通") and _is_fake_ip(ip):
                got["alive"] = "Clash污染"
            out[url] = got
        return out

    def discover_roots(self, company: str) -> dict:
        domains: List[str] = []
        urls: List[str] = []
        names: List[str] = []
        source: List[str] = []
        rows: List[dict] = []
        self._say("[根域] icplishi 公开备案 %s/company/" % ICPLISHI)
        public = fetch_icplishi_company(company, log=self._say)
        if public:
            source.append("icplishi")
            rows.extend(public)
            self._say("[根域] icplishi %s 条" % len(public))
        else:
            self._say("[根域] icplishi 无记录")
        exact = [r for r in rows if (r.get("unitName") or "").strip() == company]
        use = exact or rows
        if exact:
            self._say("[根域] 精确主体 %s 条" % len(exact))
        elif rows:
            self._say("[根域] 无精确主体，共 %s 条，只收主体含公司名的域名" % len(rows))
        for item in use:
            unit = (item.get("unitName") or "").strip()
            if exact and unit != company:
                continue
            if (not exact) and company and company not in unit and unit not in company:
                continue
            raw = (item.get("domain") or "").strip()
            if not is_valid_root(raw):
                if raw:
                    self._say("[根域] 丢弃非法 %s" % raw)
                continue
            root = root_domain(raw)
            if root in domains:
                continue
            domains.append(root)
            lic = (item.get("serviceLicence") or "").strip()
            self._say("[根域] %s  %s  %s" % (root, unit, lic))
            if unit and unit not in names:
                names.append(unit)
        if not domains:
            self._say("[根域] 备案反查空，FOFA title 兜底（丢掉邮箱/IP/公共邮箱商）")
            data = self.search('title="%s"' % fofa_escape_title(company), 50)
            for f in self._rows(data):
                raw = str(f.get("domain") or f.get("host") or "")
                if not is_valid_root(raw):
                    continue
                d = root_domain(raw)
                if d and d not in domains:
                    domains.append(d)
            if domains:
                source.append("FOFA")
        self._say("[根域] %s  %s" % ("+".join(source) or "空", "、".join(domains) or "无"))
        return {"domains": domains, "urls": urls, "site_names": names, "source": source}

    def _add_hit(self, hits: List[Hit], seen: Set[tuple], **kwargs) -> Optional[Hit]:
        host = kwargs.get("host") or ""
        port = str(kwargs.get("port") or "")
        title = kwargs.get("fofa_title") or ""
        key = (host, port, title, kwargs.get("url") or "")
        if key in seen:
            return None
        seen.add(key)
        hit = Hit(**kwargs)
        hits.append(hit)
        return hit

    def _rows(self, data: dict) -> List[dict]:
        out = []
        for item in data.get("finalResults") or []:
            f = item.get("fields") or item
            out.append(f)
        return out

    def _is_own(self, host: str, domain: str, official: Set[str]) -> bool:
        if not official:
            return False
        roots = {root_domain(x) for x in official if x and is_valid_root(x)}
        h = root_domain(host)
        d = root_domain(domain)
        if h in MAIL_ROOTS or d in MAIL_ROOTS:
            return False
        return (h in roots) or (d in roots)

    def _verdict(self, hit: Hit, company: str, official_org: str, keywords: Optional[List[str]] = None) -> None:
        title_blob = " ".join([hit.fofa_title or "", hit.live_title or ""])
        if hit.own:
            hit.verdict = "自有"
            hit.note = hit.note or "官网根域，对照基准"
            return
        if hit.alive in ("无解析", "未见注册") and not title_blob.strip():
            hit.verdict = "排除"
            hit.note = hit.note or "别名后缀未见解析/测绘"
            return
        if GAMBLE_RE.search(title_blob):
            hit.verdict = "博彩/冒备案"
            hit.note = "标题像博彩影视，不当钓鱼官网"
            return
        lookalike = False
        checks = [company] + list(keywords or [])
        for kw in checks:
            if kw and len(kw) >= 4 and (kw in (hit.fofa_title or "") or kw in (hit.live_title or "")):
                lookalike = True
                break
        alive_ok = hit.alive.startswith("通") or hit.alive.startswith("200") or hit.alive.startswith("302")
        blocked = "Cloudflare" in hit.alive or hit.alive.startswith("被拦")
        down = hit.alive in ("不通", "超时", "空回复", "TLS失败", "502") or hit.alive.startswith("不通")
        icp_no = hit.icp or ""
        icp_miss = icp_no in ("", "未收录") or icp_no.startswith("查询失败")
        org_mismatch = bool(official_org and hit.icp_org and official_org not in hit.icp_org and hit.icp_org not in official_org)

        if hit.live_title and hit.fofa_title and hit.live_title != hit.fofa_title:
            if company not in hit.live_title and company in hit.fofa_title:
                hit.verdict = "测绘过期"
                hit.note = "FOFA 标题还写公司名，活体已换皮"
                return

        if lookalike and alive_ok and (icp_miss or org_mismatch):
            hit.verdict = "可疑钓鱼"
            hit.note = "第三方活体同标题，备案未收录或主体不符"
            return
        if lookalike and blocked:
            hit.verdict = "可疑-被拦"
            hit.note = "标题或域名像官方，真页被拦"
            return
        if lookalike and down:
            hit.verdict = "可疑-不通"
            hit.note = "测绘标题像真站，本轮打不开"
            return
        if lookalike and alive_ok:
            hit.verdict = "需人工"
            hit.note = "第三方标题像公司，备案要对照"
            return
        hit.verdict = "排除"
        if not hit.note:
            hit.note = "标题不像该公司对外站"

    def run(self, cfg: HuntConfig) -> dict:
        self._stop = False
        company = (cfg.title or "").strip()
        if not company:
            raise ValueError("公司名称不能空")
        official = []
        for d in cfg.official_domains:
            if not is_valid_root(d):
                self._say("[根域] 丢弃非法输入 %s" % d)
                continue
            try:
                cleaned = domain_icp.clean_domain(d) if "." in d else d.lower()
            except ValueError:
                cleaned = root_domain(d)
            if is_valid_root(cleaned) and cleaned not in official:
                official.append(cleaned)
        hits: List[Hit] = []
        seen: Set[tuple] = set()
        queries_run: List[dict] = []
        official_org = ""
        site_names: List[str] = []
        fuzzed: List[str] = []
        official_url = (cfg.official_url or "").strip()
        if official_url and not is_valid_http_url(official_url):
            self._say("[官网] 丢弃非法 URL %s" % official_url)
            official_url = ""
        alias_found: List[str] = []

        self._say("==== 开始 公司=%s ====" % company)

        if cfg.do_roots:
            found = self.discover_roots(company)
            site_names.extend(found.get("site_names") or [])
            for d in found.get("domains") or []:
                if is_valid_root(d) and d not in official:
                    official.append(d)
            if not official_url:
                for u in found.get("urls") or []:
                    if is_valid_http_url(u):
                        official_url = u
                        break

        official_set = set(official)

        if official and cfg.do_probe:
            cand = official_candidate_urls(official, [official_url] if official_url else [])
            self._say("[官网] 拼接探测 %s 条" % len(cand))
            jobs = []
            for url in cand:
                p = urlparse(url)
                jobs.append({
                    "url": url,
                    "host": p.hostname or "",
                    "ip": "",
                    "port": str(p.port or (443 if p.scheme == "https" else 80)),
                })
            probed = self.probe_batch(jobs, cfg.probe_timeout, threads=min(20, max(6, len(jobs))))
            best = None
            scored = []
            for url in cand:
                if self._stop:
                    break
                pr = self._lookup_probe(probed, url) or {}
                host = urlparse(url).hostname or ""
                alive = pr.get("alive") or "不通"
                live = pr.get("live_title") or ""
                if GENERIC_LIVE_RE.search(live) or alive == "Clash污染":
                    live_ok = ""
                else:
                    live_ok = live
                scored.append((url, alive, live_ok, pr, host))
                if (alive.startswith("通") or str(alive).startswith("200")) and live_ok:
                    prefer_www = "www." in url
                    if not best:
                        best = (url, live_ok, prefer_www)
                    elif prefer_www and not best[2]:
                        best = (url, live_ok, True)
            if best:
                official_url = best[0]
                self._say("[官网] %s  标题「%s」" % (best[0], best[1]))
                if best[1] and best[1] not in site_names and not GENERIC_LIVE_RE.search(best[1]):
                    site_names.append(best[1])
            shown = set()
            for url, alive, live_ok, pr, host in scored:
                if best:
                    keep = url == best[0]
                else:
                    keep = not shown
                if not keep:
                    continue
                shown.add(url)
                self._add_hit(
                    hits, seen,
                    query="官网探测",
                    host=host,
                    url=url,
                    domain=root_domain(host),
                    live_title=live_ok or (pr.get("live_title") or ""),
                    alive=alive,
                    note=pr.get("note") or "",
                    own=True,
                    ip=_usable_ip(pr.get("resolved_ip") or ""),
                    port=str(urlparse(url).port or (443 if url.startswith("https") else 80)),
                    protocol="https" if url.startswith("https") else "http",
                )

        seed_titles = []
        for t in list(site_names) + [h.live_title for h in hits if h.live_title]:
            if not t or GENERIC_LIVE_RE.search(t) or JUNK_TITLE_RE.search(t):
                continue
            seed_titles.append(t)
        fuzzed = fuzz_titles(company, seed_titles)
        user_kw = [k.strip() for k in (cfg.keywords or []) if k.strip()]
        keywords = []
        for k in fuzzed + user_kw:
            if k not in keywords:
                keywords.append(k)
        if keywords:
            self._say("[标题fuzz] " + "、".join(keywords))

        def add_from_fofa(query: str, size: int, needle: str = "", title_gate: bool = True) -> None:
            if self._stop:
                return
            data = self.search(query, size=size)
            queries_run.append({
                "q": query,
                "total": data.get("total"),
                "n": len(self._rows(data)),
                "error": data.get("errmsg") if data.get("error") else "",
            })
            needles = [needle] if needle else ([company] + list(keywords))
            kept = 0
            dropped = 0
            for f in self._rows(data):
                host = str(f.get("host") or "")
                ip = str(f.get("ip") or "")
                port = str(f.get("port") or "")
                title = str(f.get("title") or "")
                if ip in ("0.0.0.0", "::") or host in ("0.0.0.0", "0.0.0.0:0") or _is_fake_ip(ip):
                    dropped += 1
                    continue
                if "@" in host or "@" in str(f.get("domain") or "") or "@" in str(f.get("link") or ""):
                    dropped += 1
                    continue
                if "protected data" in title.lower():
                    dropped += 1
                    continue
                own = self._is_own(host, str(f.get("domain") or ""), official_set)
                if title_gate and not own:
                    if _is_junk_title(title) and not _title_has_needles(title, [company]):
                        dropped += 1
                        continue
                    if not _title_has_needles(title, needles):
                        dropped += 1
                        continue
                key = (host, port, title)
                if key in seen:
                    continue
                seen.add(key)
                domain = str(f.get("domain") or "")
                proto = str(f.get("protocol") or "")
                url = str(f.get("link") or "") or build_url(host, port, proto)
                if url and "@" in url:
                    dropped += 1
                    continue
                hit = Hit(
                    query=query,
                    ip=_usable_ip(ip),
                    port=port,
                    host=host,
                    fofa_title=title,
                    url=url,
                    protocol=proto,
                    domain=domain or root_domain(host),
                    icp=str(f.get("icp") or ""),
                    own=own,
                )
                hits.append(hit)
                kept += 1
            if dropped:
                self._say("[FOFA] 丢掉无关/垃圾 %s 条，留 %s  %s" % (dropped, kept, query))

        if cfg.do_exact:
            add_from_fofa('title="%s"' % fofa_escape_title(company), cfg.size, needle=company)
            extra_titles = []
            for t in site_names:
                t = (t or "").strip()
                if t and t != company and t not in extra_titles and not GENERIC_LIVE_RE.search(t):
                    extra_titles.append(t)
            for t in extra_titles[:3]:
                add_from_fofa('title="%s"' % fofa_escape_title(t), min(cfg.size, 40), needle=t)

        if cfg.do_keywords:
            for kw in keywords:
                if self._stop:
                    break
                add_from_fofa('title="%s"' % fofa_escape_title(kw), min(cfg.size, 50), needle=kw)

        if cfg.do_suffix:
            names = list(official)
            extra = []
            for a in cfg.alias_domains:
                if not is_valid_root(a):
                    continue
                try:
                    extra.append(domain_icp.clean_domain(a))
                except ValueError:
                    extra.append(root_domain(a))
            names.extend(extra)
            variants = suffix_variants(names)
            alias_found = [v for v in extra + variants if v and v not in official_set]
            for name in alias_found:
                if self._stop:
                    break
                add_from_fofa('host="%s"' % name, 20, title_gate=False)
            if cfg.do_probe:
                have = {root_domain(h.domain or h.host) for h in hits}
                for name in alias_found:
                    if name in have:
                        continue
                    url = "https://www.%s/" % name
                    self._add_hit(
                        hits, seen,
                        query="别名后缀",
                        host="www." + name,
                        url=url,
                        domain=name,
                        own=False,
                        note="改后缀探测是否注册",
                        protocol="https",
                        port="443",
                    )

        icp_targets: List[Hit] = []
        if cfg.do_probe:
            jobs: List[dict] = []
            if official_url:
                parsed = urlparse(official_url)
                jobs.append({
                    "url": official_url,
                    "host": parsed.hostname or "",
                    "ip": "",
                    "port": str(parsed.port or (443 if parsed.scheme == "https" else 80)),
                })
            pending: List[Hit] = []
            for hit in hits:
                if hit.alive and hit.alive not in ("", "未探活"):
                    continue
                pending.append(hit)

            def probe_rank(h: Hit) -> tuple:
                blob = " ".join([h.fofa_title or "", h.live_title or ""])
                like = _title_has_needles(blob, [company] + list(keywords))
                suffix = h.query == "别名后缀"
                return (0 if like else 1, 0 if suffix else 1, h.url)

            pending.sort(key=probe_rank)
            for hit in pending[: cfg.max_probe]:
                jobs.append({
                    "url": hit.url,
                    "host": _norm_host(hit.host),
                    "ip": hit.ip,
                    "port": hit.port,
                })
            probed = self.probe_batch(jobs, cfg.probe_timeout, threads=min(30, max(8, len(jobs)))) if jobs else {}
            if official_url:
                pr = self._lookup_probe(probed, official_url) or {}
                if pr:
                    self._say("[基准] %s  %s  %s" % (pr.get("alive"), pr.get("live_title"), pr.get("note")))
            probed_n = 0
            for hit in hits:
                if hit.alive and hit.alive not in ("", "未探活"):
                    continue
                if probed_n >= cfg.max_probe:
                    hit.alive = "未探活(超上限)"
                    continue
                pr = self._lookup_probe(probed, hit.url)
                probed_n += 1
                if not pr:
                    hit.alive = "不通"
                    continue
                hit.alive = pr.get("alive") or "不通"
                if pr.get("live_title"):
                    hit.live_title = pr["live_title"]
                if pr.get("note"):
                    hit.note = pr["note"]
            for hit in hits:
                if hit.query == "别名后缀" and not hit.fofa_title and not hit.live_title:
                    if hit.alive in ("不通", "超时", "空回复", "TLS失败", ""):
                        hit.alive = "未见注册"
                        hit.note = "改后缀未见解析/测绘/活体"
        else:
            for hit in hits:
                if not hit.alive:
                    hit.alive = "未探活"
        checks = [company] + list(keywords)
        for hit in hits:
            if not cfg.do_icp or hit.own:
                continue
            blob = " ".join([hit.fofa_title or "", hit.live_title or ""])
            like = _title_has_needles(blob, checks)
            suffix_live = hit.query == "别名后缀" and hit.alive.startswith("通")
            if like or suffix_live or (hit.alive.startswith("通") and not _is_junk_title(blob)):
                icp_targets.append(hit)

        seen_icp: Set[str] = set()
        if cfg.do_icp:
            if official:
                lic, org = self.icp(official[0])
                official_org = org
                self._say("[备案] 官网根域 %s  %s  %s" % (official[0], lic, org))
            for hit in icp_targets:
                if self._stop:
                    break
                root = root_domain(hit.domain or hit.host)
                if not root or root in seen_icp:
                    if root in self._icp_cache:
                        hit.icp, hit.icp_org = self._icp_cache[root]
                    continue
                seen_icp.add(root)
                self._say("[备案] %s" % root)
                lic, org = self.icp(root)
                hit.icp, hit.icp_org = lic, org
            # fill cache onto siblings
            for hit in hits:
                root = root_domain(hit.domain or hit.host)
                if root in self._icp_cache and not hit.own:
                    hit.icp, hit.icp_org = self._icp_cache[root]

        for hit in hits:
            self._verdict(hit, company, official_org, keywords)

        summary = self.summarize(company, official, hits, queries_run, keywords, official_url)
        self._say("==== 结束 ====")
        self._say(summary)
        return {
            "company": company,
            "official_domains": official,
            "official_url": official_url,
            "official_org": official_org,
            "keywords": keywords,
            "alias_domains": alias_found,
            "site_names": site_names,
            "queries": queries_run,
            "hits": hits,
            "summary": summary,
        }

    def summarize(self, company: str, official: List[str], hits: List[Hit], queries: List[dict], keywords: Optional[List[str]] = None, official_url: str = "") -> str:
        n = len(hits)
        own = [h for h in hits if h.verdict == "自有"]
        phish = [h for h in hits if h.verdict == "可疑钓鱼"]
        blocked = [h for h in hits if h.verdict == "可疑-被拦"]
        down = [h for h in hits if h.verdict == "可疑-不通"]
        stale = [h for h in hits if h.verdict == "测绘过期"]
        gamble = [h for h in hits if h.verdict == "博彩/冒备案"]
        alias_hits = [h for h in hits if h.query == "别名后缀"]
        alias_live = [h for h in alias_hits if h.live_title]
        lines = []
        lines.append("公司：「%s」  官网根域：%s" % (company, "、".join(official) or "未填"))
        if official_url:
            lines.append("官网：%s" % official_url)
        if keywords:
            lines.append("fuzz 标题：%s" % "、".join(keywords))
        lines.append("测绘命中 %s 条（去重后）。精确 title 第三方克隆：%s。" % (
            n, "有" if any(h.verdict == "可疑钓鱼" and company in (h.fofa_title or "") for h in phish) else "未见活体第三方同标题",
        ))
        if phish:
            lines.append("可疑钓鱼（活体）：")
            for h in phish[:12]:
                lines.append("  %s  |  %s  |  %s  | 备案 %s %s" % (h.url, h.alive, h.live_title or h.fofa_title, h.icp, h.icp_org))
        if blocked:
            lines.append("可疑被拦： " + "；".join(h.url for h in blocked[:8]))
        if down:
            lines.append("标题像真站但不通： " + "；".join(h.url for h in down[:8]))
        if stale:
            lines.append("测绘过期 %s 条。" % len(stale))
        if gamble:
            lines.append("博彩/冒备案 %s 条，不按假官网算。" % len(gamble))
        if alias_live:
            lines.append("别名已注册且有标题：")
            for h in alias_live[:12]:
                lines.append("  %s  |  %s  |  %s" % (h.domain or h.host, h.alive, h.live_title))
        unseen = [h for h in alias_hits if h.alive == "未见注册"]
        if unseen:
            lines.append("别名未见注册 %s 个：%s" % (len(unseen), "、".join((h.domain or h.host) for h in unseen[:15])))
        lines.append("自有对照 %s 条。" % len(own))
        zero = [q for q in queries if not q.get("total") and not q.get("error")]
        if zero:
            lines.append("0 条的语句 %s 条，只说明 FOFA 当前索引空，不说明没有站。" % len(zero))
        lines.append("Hunter/Quake/WHOIS 本工具未跑。")
        return "\n".join(lines)


def hits_to_rows(hits: List[Hit]) -> List[List[str]]:
    header = ["判定", "URL", "FOFA标题", "活体标题", "IP", "端口", "存活", "备案号", "备案主体", "查询语句", "说明"]
    rows = [header]
    for h in hits:
        rows.append([
            h.verdict, h.url, h.fofa_title, h.live_title, h.ip, h.port,
            h.alive, h.icp, h.icp_org, h.query, h.note,
        ])
    return rows


def export_xlsx(path: str, result: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "结果"
    rows = hits_to_rows(result.get("hits") or [])
    fills = {
        "可疑钓鱼": "FF6B6B",
        "可疑-被拦": "E67E22",
        "可疑-不通": "F4D03F",
        "自有": "7DCEA0",
        "博彩/冒备案": "BB8FCE",
        "测绘过期": "AED6F1",
        "需人工": "F5B041",
        "排除": "D5D8DC",
        "未见注册": "EEEEEE",
    }
    thin = Border(
        left=Side(style="thin", color="B0B0B0"),
        right=Side(style="thin", color="B0B0B0"),
        top=Side(style="thin", color="B0B0B0"),
        bottom=Side(style="thin", color="B0B0B0"),
    )
    wrap = Alignment(wrap_text=True, vertical="top")
    head_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="微软雅黑", size=10)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row, 1):
            cell = ws.cell(row=i, column=j, value=v)
            cell.alignment = wrap
            cell.border = thin
            cell.font = head_font if i == 1 else body_font
            if i == 1:
                cell.fill = PatternFill("solid", fgColor="2F5496")
            elif i > 1:
                color = fills.get(str(row[0]), "FFFFFF")
                cell.fill = PatternFill("solid", fgColor=color)
        ws.row_dimensions[i].height = 22 if i == 1 else 40
    widths = [14, 42, 36, 36, 18, 8, 18, 22, 22, 28, 36]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    ws2 = wb.create_sheet("分析")
    ws2["A1"] = result.get("summary") or ""
    ws2["A1"].alignment = Alignment(wrap_text=True, vertical="top")
    ws2.column_dimensions["A"].width = 120
    ws2.row_dimensions[1].height = 220

    ws3 = wb.create_sheet("查询语句")
    ws3.append(["语句", "total", "返回", "错误"])
    for q in result.get("queries") or []:
        ws3.append([q.get("q"), q.get("total"), q.get("n"), q.get("error")])
    wb.save(path)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="TwinTitle 同题猎手（无头）")
    p.add_argument("--title", default="", help="公司对外标题 / 全称")
    p.add_argument("--official", default="", help="官网根域，逗号或换行分隔")
    p.add_argument("--url", default="", help="官网 URL，作探活基准")
    p.add_argument("--alias", default="", help="别名根域")
    p.add_argument("--keywords", default="", help="扩搜关键字")
    p.add_argument("--out", default="", help="导出 xlsx 路径")
    p.add_argument("--size", type=int, default=50)
    p.add_argument("--no-roots", action="store_true")
    p.add_argument("--no-probe", action="store_true")
    p.add_argument("--no-icp", action="store_true")
    p.add_argument("--no-suffix", action="store_true")
    p.add_argument("--no-keywords", action="store_true")
    p.add_argument("--validate", action="store_true", help="只测 FOFA 连通")
    args = p.parse_args()

    def _log(msg: str) -> None:
        print(msg, flush=True)

    eng = TitlePhishEngine(log=_log)
    if args.validate:
        info = eng.api.validate()
        print(info)
        return
    if not (args.title or "").strip():
        p.error("需要 --title")
    cfg = HuntConfig(
        title=args.title.strip(),
        official_domains=split_list(args.official),
        official_url=(args.url or "").strip(),
        alias_domains=split_list(args.alias),
        keywords=split_list(args.keywords),
        do_roots=not args.no_roots,
        do_exact=True,
        do_probe=not args.no_probe,
        do_icp=not args.no_icp,
        do_suffix=not args.no_suffix,
        do_keywords=not args.no_keywords,
        size=args.size,
    )
    result = eng.run(cfg)
    if args.out:
        export_xlsx(args.out, result)
        print("xlsx " + args.out)


if __name__ == "__main__":
    main()

