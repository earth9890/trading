"""Download NSE UDiFF F&O bhavcopies (resumable, ~1 req/s) -> data/fo_bhav/YYYYMMDD.zip. Usage: fo_fetch.py START END"""
import sys, time, datetime as dt, pathlib, urllib.request, urllib.error
D = pathlib.Path(__file__).parent / "data/fo_bhav"; D.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
d, end = (dt.date.fromisoformat(a) for a in sys.argv[1:3])
while d <= end:
    f, hol = D / f"{d:%Y%m%d}.zip", D / f"{d:%Y%m%d}.none"
    if d.weekday() < 5 and not f.exists() and not hol.exists():
        url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
        for k in range(4):
            try:
                b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()
                f.write_bytes(b); break
            except urllib.error.HTTPError as e:
                if e.code in (403, 404): hol.write_text(str(e.code)); break  # holiday / missing
                time.sleep(3 * (k + 1))
            except Exception: time.sleep(3 * (k + 1))
        time.sleep(1)
    d += dt.timedelta(1)
print("done")
