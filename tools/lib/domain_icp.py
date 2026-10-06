# -*- coding: utf-8 -*-
"""从 seo.chinaz.com 取域名备案号和备案主体。"""
import argparse
import re
import sys
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
LICENSE = re.compile(r"""var\s+license\s*=\s*(['"])(.*?)\1""", re.S)
COMPANY = re.compile(
    r"""<([a-zA-Z0-9]+)\b[^>]*\bid\s*=\s*(['"])company\2[^>]*>(.*?)</\1>""",
    re.I | re.S,
)
TAGS = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def clean_domain(raw):
    text = raw.strip().lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0].split("?", 1)[0].strip(".")
    if not text or " " in text or "." not in text:
        raise ValueError("非法域名: %s" % raw.strip())
    return text


def load_domains(args):
    items = list(args.domains)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            items.extend(handle.read().splitlines())
    seen = []
    for item in items:
        if not item.strip() or item.strip().startswith("#"):
            continue
        name = clean_domain(item)
        if name not in seen:
            seen.append(name)
    if not seen:
        raise SystemExit("没有域名")
    return seen


def fetch(domain, timeout):
    url = "https://seo.chinaz.com/" + domain
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def text_of(fragment):
    return WS.sub(" ", TAGS.sub("", fragment)).strip()


def parse(html):
    license_no = ""
    company = ""
    found = LICENSE.search(html)
    if found:
        license_no = found.group(2).strip()
    for found in COMPANY.finditer(html):
        company = text_of(found.group(3))
        if company:
            break
    return license_no, company


def configure_stdout():
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        try:
            out.reconfigure(encoding="utf-8", newline="\n", errors="replace")
        except (OSError, ValueError):
            pass
    return out


def main():
    parser = argparse.ArgumentParser(description="查询域名备案")
    parser.add_argument("domains", nargs="*")
    parser.add_argument("-f", "--file")
    parser.add_argument("-o", "--output")
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args()
    domains = load_domains(args)
    out = configure_stdout()
    sink = open(args.output, "w", encoding="utf-8", newline="\n") if args.output else None
    try:
        header = "域名\t备案号\t备案主体\n"
        out.write(header)
        out.flush()
        if sink:
            sink.write(header)
        for domain in domains:
            code, html = fetch(domain, args.timeout)
            if code >= 400:
                raise RuntimeError("HTTP %s %s" % (code, domain))
            license_no, company = parse(html)
            line = "%s\t%s\t%s\n" % (domain, license_no or "未收录", company)
            out.write(line)
            out.flush()
            if sink:
                sink.write(line)
    finally:
        if sink:
            sink.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        sys.stderr.write("%s\n" % exc)
        sys.exit(2)
