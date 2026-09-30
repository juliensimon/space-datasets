import json, requests, time
B = "https://fccprod.servicenowservices.com"
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", "Accept": "application/json"})
SKIP = {"template", "css", "client_script", "link", "script", "server_script", "option_schema", "demo_data"}
KW = ("freq", "service", "descr", "band", "emission", "orbit", "satell", "narrative")

def walk(o, path, out):
    if isinstance(o, dict):
        if set(o) >= {"display_value", "label"}:
            if any(k in (path + str(o["label"])).lower() for k in KW):
                out.append(f"{path} [{o['label']}] = {str(o['display_value'])[:300]!r}")
            return
        for k, v in o.items():
            if k in SKIP: continue
            p = f"{path}.{k}"
            if isinstance(v, (str, int, float)) and any(x in k.lower() for x in KW) and str(v).strip():
                out.append(f"{p} = {str(v)[:300]!r}")
            walk(v, p, out)
    elif isinstance(o, list):
        for i, v in enumerate(o[:60]):
            walk(v, f"{path}[{i}]", out)

for fn in ("SAT-LOA-20190704-00057", "SAT-LOA-20161115-00118"):
    j = s.get(f"{B}/api/now/sp/page", params={"id": "ibfs_application_summary", "number": fn}, timeout=60).json()
    out = []
    walk(j, "", out)
    print(f"\n######## {fn}: {len(out)} hits")
    for line in out[:150]: print("  ", line)
    # tab widget names/ids and their data keys
    def tabs(o, path=""):
        if isinstance(o, dict):
            if o.get("id") == "ibfs-tabs" or o.get("name") == "IBFS Tabs":
                for i, w in enumerate((o.get("data") or {}).get("widgets", [])):
                    ww = w.get("widget", w) if isinstance(w, dict) else {}
                    print(f"   TAB[{i}] name={ww.get('name')!r} id={ww.get('id')!r} keys={sorted((ww.get('data') or {}).keys())[:30]} topkeys={sorted(w.keys())[:20] if isinstance(w, dict) else None}")
            for k, v in o.items():
                if k not in SKIP: tabs(v, path + "." + k)
        elif isinstance(o, list):
            for v in o: tabs(v, path)
    tabs(j)
    time.sleep(2)
raise SystemExit(1)
