import json, requests, time
B = "https://fccprod.servicenowservices.com"
SEED = [f["file_number"] for f in json.load(open("scripts/data/fcc_ngso_seed.json"))["filings"]]
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", "Accept": "application/json"})

def widgets(o):
    if isinstance(o, dict):
        if "widget" in o and isinstance(o.get("widget"), dict):
            yield o["widget"]
        for v in o.values():
            yield from widgets(v)
    elif isinstance(o, list):
        for v in o:
            yield from widgets(v)

def show(d, pre, depth=0):
    if depth > 4: return
    if isinstance(d, dict):
        if set(d) >= {"display_value", "label"}:
            print(f"{pre} [{d['label']}] = {str(d['display_value'])[:160]!r}")
            return
        for k, v in d.items():
            show(v, f"{pre}.{k}", depth+1)
    elif isinstance(d, list):
        print(f"{pre} (list len={len(d)})")
        for i, v in enumerate(d[:6]): show(v, f"{pre}[{i}]", depth+1)
    elif isinstance(d, (str, int, float, bool)) or d is None:
        print(f"{pre} = {str(d)[:160]!r}")

for n, fn in enumerate(SEED):
    r = s.get(f"{B}/api/now/sp/page", params={"id": "ibfs_application_summary", "number": fn}, timeout=60)
    print(f"\n######## {fn} -> {r.status_code}, {len(r.text)} bytes")
    j = r.json()
    for w in widgets(j):
        d = w.get("data") or {}
        if not d: continue
        print(f"--- widget name={w.get('name')!r} id={w.get('id')!r} keys={sorted(d)[:40]}")
        if n < 2 or "summary" in d:
            show(d, "   data")
    time.sleep(2)
raise SystemExit(1)
