import requests
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
FN = "SAT-LOA-20190704-00057"
URLS = [
    f"https://fcc.report/IBFS/{FN}",
    "https://fcc.report/",
    "https://fcc.report/robots.txt",
    f"https://licensing.fcc.gov/cgi-bin/ws.exe/prod/ib/forms/reports/swr031b.hts?q_set=V_SITE_ANTENNA_FREQ.file_numberC/File+Number/%3D/{FN}&prepare=&column=V_SITE_ANTENNA_FREQ.file_numberC/File+Number",
    f"https://licensing.fcc.gov/myibfs/searchApplication.do?fileNumber={FN}",
    f"https://licensing.fcc.gov/myibfs/displayLicense.do?filingKey=-{FN}",
    "https://icfs.fcc.gov/",
    f"https://icfs.fcc.gov/ecfs/api/filings?file_number={FN}",
    f"https://publicapi.fcc.gov/ecfs/filings?proceedings.name={FN}",
    f"https://fccprod.servicenowservices.com/icfs?id=ibfs_application_summary&number={FN}",
]
for ua in (UA, "space-datasets/1.0 (+https://github.com/juliensimon/space-datasets)"):
    for u in URLS:
        try:
            r = requests.get(u, headers={"User-Agent": ua, "Accept": "text/html,*/*"}, timeout=30, allow_redirects=True)
            hdr = {k: v for k, v in r.headers.items() if k.lower() in ("server", "cf-ray", "cf-mitigated", "content-type", "location", "x-cache")}
            body = " ".join(r.text[:400].split())
            print(f"[{ua[:12]}] {r.status_code} {r.url}\n   hdr={hdr}\n   body={body}\n")
        except Exception as e:
            print(f"[{ua[:12]}] ERR {u}: {e}\n")
raise SystemExit(1)
