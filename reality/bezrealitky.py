"""Stahování nabídek z Bezrealitek (GraphQL API jejich webu)."""
import json
import time
import urllib.request

import config

API = "https://api.bezrealitky.cz/graphql/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36",
           "Origin": "https://www.bezrealitky.cz", "Referer": "https://www.bezrealitky.cz/",
           "Content-Type": "application/json"}
QUERY = """query($o:[OfferType],$e:[EstateType],$l:Int,$f:Int){listAdverts(offerType:$o,estateType:$e,limit:$l,offset:$f,
order:TIMEORDER_DESC,currency:CZK){totalCount list{id uri disposition surface price charges city(locale:CS)
address(locale:CS) gps{lat lng} mainImage{url(filter:RECORD_THUMB)}}}}"""
PAGE = 200

DISPOZICE = {"GARSONIERA": "1+kk", "OSTATNI": "Atypický", "UNDEFINED": "Atypický"}


def dispozice(kod):
    """DISP_2_KK -> 2+kk, DISP_3_1 -> 3+1, DISP_6_* a víc -> 6 a více."""
    if kod in DISPOZICE:
        return DISPOZICE[kod]
    casti = (kod or "").replace("DISP_", "").split("_")
    if len(casti) == 2 and casti[0].isdigit():
        if int(casti[0]) >= 6:
            return "6 a více"
        return f"{casti[0]}+{'kk' if casti[1] == 'KK' else '1'}"
    return "Atypický"


def search(offer, estate="BYT"):
    out, offset = [], 0
    while True:
        body = json.dumps({"query": QUERY, "variables": {"o": [offer], "e": [estate], "l": PAGE, "f": offset}}).encode()
        for pokus in range(3):
            try:
                req = urllib.request.Request(API, data=body, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.load(r)["data"]["listAdverts"]
                break
            except Exception:
                if pokus == 2:
                    raise
                time.sleep(3 * (pokus + 1))
        out.extend(d["list"])
        offset += len(d["list"])  # API vrací max. 100 na stránku, i když chceš víc
        time.sleep(config.REQUEST_PAUSE)
        if not d["list"] or offset >= d["totalCount"]:
            return out


def url(r):
    return f"https://www.bezrealitky.cz/nemovitosti-byty-domy/{r['uri']}"
