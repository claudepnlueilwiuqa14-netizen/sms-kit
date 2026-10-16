#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smskit —— 多源接码器（免费站 + 商业平台）
源:
  free_smstome     smstome.com（免费公开号）
  free_rso         receive-sms-online.info（免费公开号）
  smsactivate      sms-activate.org（商业，需 API key，TG 专用干净号）
  5sim             5sim.net（商业，需 token）
用法:
  python smskit.py free                  # 列免费站可用号
  python smskit.py buy smsactivate TG    # 商业平台买 TG 号（需 key）
  python smskit.py wait <order_id>       # 轮询等验证码
"""
import json, os, re, sys, time, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "smskit_config.json")
PROXY = "http://127.0.0.1:7897"

_opener = None
def opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    return _opener

def get(url, timeout=20, data=None, headers=None):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with opener().open(req, timeout=timeout) as r:
        return r.read()

def load_cfg():
    if os.path.exists(CFG):
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    return {}

# ---------- 免费站 ----------

def free_smstome():
    """smstome.com 抓可用号"""
    html = get("https://smstome.com/").decode("utf-8", "ignore")
    rows = re.findall(
        r'href="(/(?:country/[^"]+|us/[^"]+))"[^>]*>.*?</a>.*?'
        r'<td[^>]*>(\+?\d[\d\s-]{6,})</td>', html, re.S)
    # 宽松兜底: 抓所有 + 号段
    if not rows:
        rows = [(m, m) for m in re.findall(r'\+1\d{10}', html)]
    return [{"src": "smstome", "phone": p.strip(), "url":
             "https://smstome.com" + u} for u, p in rows[:40]]

def free_rso():
    """receive-sms-online.info 抓可用号"""
    html = get("https://receive-sms-online.info/").decode("utf-8", "ignore")
    rows = re.findall(r'href="(/(?:us|uk|ca|fr|de|ru|nl|pl|es|se)/\d+/)"[^>]*>\s*'
                      r'(\+?\d[\d\s-]{6,})', html)
    return [{"src": "rso", "phone": p.strip(), "url":
             "https://receive-sms-online.info" + u} for u, p in rows[:40]]

def free_numbers():
    out = []
    for fn in (free_smstome, free_rso):
        try:
            out += fn()
        except Exception as e:
            print("[warn]", fn.__name__, e)
    return out

def check_messages(url):
    """抓某号的收件箱"""
    try:
        html = get(url).decode("utf-8", "ignore")
    except Exception:
        return []
    rows = re.findall(
        r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>',
        html, re.S)
    msgs = []
    for sender, body in rows[:10]:
        txt = re.sub(r"<[^>]+>", "", body).strip()
        if txt:
            msgs.append({"from": re.sub(r"<[^>]+>", "", sender).strip(),
                         "text": txt[:200]})
    return msgs

# ---------- sms-activate ----------

SA = "https://api.sms-activate.ae/stubs/handler_api.php"

def sa(method, params=None):
    c = load_cfg()
    key = c.get("smsactivate_key", "")
    if not key:
        raise SystemExit("[!] 缺 sms-activate API key: python smskit.py setkey smsactivate <key>")
    p = {"api_key": key}
    if params: p.update(params)
    url = SA + "?" + urllib.parse.urlencode({**p, "action": method})
    body = get(url).decode("utf-8", "ignore")
    if body.startswith("ACCESS_"): body = body[len("ACCESS_"):]
    return body

def sa_buy(service, country=0):
    """买号: service=TG(Telegram)/ig/wa...; country=0 俄罗斯 / 其他查 getCountries"""
    r = sa("getNumberV2", {"service": service, "country": country})
    try:
        d = json.loads(r)
        return d  # {"activationId":..,"phoneNumber":"..", ...}
    except Exception:
        return {"raw": r}

def sa_wait(order_id, timeout=600):
    """轮询等验证码"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = sa("getStatus", {"id": order_id})
        if r.startswith("STATUS_OK:"):
            return r.split(":", 1)[1]
        if r == "STATUS_CANCEL":
            return None
        time.sleep(5)
    return None

# ---------- 5sim ----------

FIVESIM = "https://5sim.net/v1"

def fs(endpoint, params=None, method="GET"):
    c = load_cfg()
    tok = c.get("fivesim_token", "")
    if not tok:
        raise SystemExit("[!] 缺 5sim token: python smskit.py setkey fivesim <token>")
    url = FIVESIM + endpoint
    if params: url += "?" + urllib.parse.urlencode(params)
    data = None
    if method == "POST":
        data = b""
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": "Bearer " + tok,
                 "Accept": "application/json",
                 "User-Agent": "Mozilla/5.0"})
    with opener().open(req, timeout=25) as r:
        return json.load(r)

def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "setkey":
        cfg = {**load_cfg(), a[1] + "_key" if a[1] == "smsactivate" else a[1] + "_token": a[2]}
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        print("[ok]", a[1], "凭证已存"); return
    if cmd == "free":
        nums = free_numbers()
        print(json.dumps({"count": len(nums), "rows": nums}, ensure_ascii=False, indent=1))
    elif cmd == "check":
        print(json.dumps(check_messages(a[1]), ensure_ascii=False, indent=1))
    elif cmd == "buy":
        platform = a[1]; svc = a[2] if len(a) > 2 else "TG"
        if platform == "smsactivate":
            print(json.dumps(sa_buy(svc), ensure_ascii=False, indent=1))
        elif platform == "fivesim":
            country = a[3] if len(a) > 3 else "russia"
            print(json.dumps(fs("/user/buy/activation/%s/any/telegram" % country),
                             ensure_ascii=False, indent=1))
    elif cmd == "wait":
        print(json.dumps({"code": sa_wait(a[1])}, ensure_ascii=False))
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
