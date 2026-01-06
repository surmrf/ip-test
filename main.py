#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import platform
import subprocess
import re
import json
import time
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

geo_lock = Lock()
last_geo_time = 0

def ping_avg_loss(ip: str, timeout_ms=1200, count=4):
    sysname = platform.system().lower()
    if "windows" in sysname:
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), ip]
    else:
        timeout_s = max(1, int(round(timeout_ms / 1000)))
        cmd = ["ping", "-c", str(count), "-W", str(timeout_s), ip]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout or "") + (p.stderr or "")
    except Exception:
        return None, None

    loss = None
    avg = None

    m = re.search(r"(\d+)%\s*packet loss", out)
    if m:
        loss = int(m.group(1))
    else:
        m = re.search(r"\((\d+)%\s*loss\)", out, re.IGNORECASE)
        if m:
            loss = int(m.group(1))

    m = re.search(r"=\s*[\d\.]+/([\d\.]+)/[\d\.]+/[\d\.]+\s*ms", out)
    if m:
        avg = float(m.group(1))
    else:
        m = re.search(r"Average\s*=\s*(\d+)\s*ms", out, re.IGNORECASE)
        if m:
            avg = float(m.group(1))

    return avg, loss

def geo(ip: str, timeout=3.5):
    global last_geo_time
    with geo_lock:
        elapsed = time.time() - last_geo_time
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)
        last_geo_time = time.time()

    url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,isp,as,query"
    req = Request(url, headers={"User-Agent": "ip-test/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if data.get("status") != "success":
            return None
        return data
    except (HTTPError, URLError, Exception):
        return None

def test_ip(ip: str):
    with ThreadPoolExecutor(max_workers=2) as pool:
        ping_future = pool.submit(ping_avg_loss, ip)
        geo_future = pool.submit(geo, ip)
        avg, loss = ping_future.result()
        g = geo_future.result()
    return ip, avg, loss, g

def pad(s, w):
    s = "" if s is None else str(s)
    return (s[:w-1] + "…") if len(s) > w else s.ljust(w)

def format_row(ip, avg, loss, g):
    country = region = city = isp_as = ""
    if g:
        country = g.get("country", "")
        region = g.get("regionName", "")
        city = g.get("city", "")
        isp_as = " / ".join([x for x in [g.get("isp"), g.get("as")] if x])
    else:
        isp_as = "GEO_LOOKUP_FAILED"
    return "  ".join([
        pad(ip, 16),
        pad(f"{avg:.2f}" if avg is not None else "NA", 9),
        pad(str(loss) if loss is not None else "NA", 8),
        pad(country, 10),
        pad(region, 12),
        pad(city, 12),
        pad(isp_as, 34),
    ])

def main():
    ip_list = sys.argv[1:]
    if not ip_list:
        print("Usage: python3 main.py <ip1> <ip2> ...")
        sys.exit(1)

    headers = ["IP", "Avg(ms)", "Loss(%)", "国家", "省/州", "城市", "ISP / AS"]
    print(
        pad(headers[0], 16), pad(headers[1], 9), pad(headers[2], 8),
        pad(headers[3], 10), pad(headers[4], 12), pad(headers[5], 12), pad(headers[6], 34),
        sep="  "
    )
    print("-" * 110)

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(test_ip, ip): ip for ip in ip_list}
        for future in as_completed(futures):
            ip, avg, loss, g = future.result()
            results[ip] = (avg, loss, g)

    for ip in ip_list:
        avg, loss, g = results[ip]
        print(format_row(ip, avg, loss, g))

if __name__ == "__main__":
    main()
