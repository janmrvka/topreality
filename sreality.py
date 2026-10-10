"""Stahování nabídek ze Srealit (API, které používá jejich web)."""
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request

import config

API = "https://www.sreality.cz/api/v1/estates"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36",
      "Accept": "application/json"}
REGIONS = range(1, 15)
PAGE = 500  # API vrací max. 10 000 výsledků na dotaz, proto se stahuje po krajích

TYP_URL = {1: "byt", 2: "dum", 4: "komercni"}


def _get(url):
    for pokus in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except Exception:
            if pokus == 2:
                raise
            time.sleep(3 * (pokus + 1))


def search(main_cb, type_cb, sub_cb=None, price_to=None):
    """Vrátí všechny nabídky dané kategorie v ČR (po krajích, stránkovaně)."""
    out = []
    for region in REGIONS:
        offset = 0
        while True:
            q = {"category_main_cb": main_cb, "category_type_cb": type_cb,
                 "locality_region_id": region, "limit": PAGE, "offset": offset}
            if sub_cb:
                q["category_sub_cb"] = sub_cb
            if price_to:
                q["price_to"] = price_to
            d = _get(f"{API}/search?{urllib.parse.urlencode(q)}")
            res = d.get("results") or []
            out.extend(res)
            offset += PAGE
            time.sleep(config.REQUEST_PAUSE)
            if not res or offset >= min(d["pagination"]["total"], 10_000):
                break
    return out


def detail(hash_id):
    return _get(f"{API}/{hash_id}").get("result") or {}


def plocha(r):
    # "Prodej bytu 4+1 121 m²": číslo nesmí navazovat na dispozici, jinak vyjde 1 121
    m = re.search(r"(?<![\d+])(\d{1,3}(?:[  ]\d{3})*)\s*m²", r.get("advert_name", ""))
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def url(r):
    typ = "prodej" if r["category_type_cb"]["value"] == 1 else "pronajem"
    kat = TYP_URL.get(r["category_main_cb"]["value"], "x")
    sub = unicodedata.normalize("NFKD", r["category_sub_cb"]["name"].lower()).encode("ascii", "ignore").decode()
    sub = urllib.parse.quote(sub.replace(" ", "-"))
    obec = r["locality"].get("city_seo_name") or "x"
    return f"https://www.sreality.cz/detail/{typ}/{kat}/{sub}/{obec}/{r['hash_id']}"


def obrazek(r):
    imgs = r.get("advert_images") or []
    return ("https:" + imgs[0] + "?fl=res,400,300,3|shr,,20|jpg,90") if imgs else None
