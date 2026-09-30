import json, requests
B = "https://fccprod.servicenowservices.com"
P = "6865628b1bd2625069c154e2604bcbf2"
FN = "SAT-LOA-20190704-00057"
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                  "Accept": "application/json"})
s.get(f"{B}/icfs?id=ibfs_application_summary&number={FN}", timeout=30)
URLS = [
    f"{B}/api/now/sp/page?id=ibfs_application_summary&number={FN}&portal_id={P}",
    f"{B}/api/now/sp/page?id=ibfs_application_summary&number={FN}",
    f"{B}/api/now/table/x_g_fmc_ibfs_filing?sysparm_query=file_number={FN}&sysparm_limit=1",
    f"{B}/icfs?id=ibfs_search",
]
for u in URLS:
    try:
        r = s.get(u, timeout=60)
        print(f"== {r.status_code} {u} ({len(r.text)} bytes, {r.headers.get('content-type')})")
        t = r.text
        for kw in ("Kuiper", "KUIPER", "Date Filed", "date_filed", "Grant", "Status", "error"):
            i = t.find(kw)
            if i >= 0:
                print(f"   [{kw}] ...{' '.join(t[max(0,i-300):i+500].split())}...")
        print("   HEAD:", " ".join(t[:1500].split()))
        if "json" in (r.headers.get("content-type") or ""):
            j = r.json()
            def walk(o, path="", depth=0):
                if depth > 6: return
                if isinstance(o, dict):
                    for k, v in o.items():
                        if isinstance(v, (dict, list)): walk(v, f"{path}.{k}", depth+1)
                        elif isinstance(v, str) and v and len(v) < 200 and any(x in k.lower() for x in ("name","title","widget","id","file","date","status","applicant","value","display")):
                            print(f"   {path}.{k} = {v!r}")
                elif isinstance(o, list):
                    for i, v in enumerate(o[:40]): walk(v, f"{path}[{i}]", depth+1)
            walk(j)
    except Exception as e:
        print("ERR", u, e)
raise SystemExit(1)
