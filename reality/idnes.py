"""Stahování nabídek z iDNES Reality (HTML výpis, regex).

Hlavičky proti antibotu, zpracování useknuté odpovědi a konec stránkování převzaté
ze šablony byty-bot (MIT, (c) 2026 MarketaAnt, ryslinkova):
https://github.com/ryslinkova/byty-bot-template
"""
import http.client
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import config

ROOT = "https://reality.idnes.cz"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Referer": "https://reality.idnes.cz/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}
KRAJE = ["praha", "stredocesky-kraj", "jihocesky-kraj", "plzensky-kraj", "karlovarsky-kraj",
         "ustecky-kraj", "liberecky-kraj", "kralovehradecky-kraj", "pardubicky-kraj",
         "kraj-vysocina", "jihomoravsky-kraj", "olomoucky-kraj", "zlinsky-kraj",
         "moravskoslezsky-kraj"]
MAX_PAGES = 400

_HREF = re.compile(r'href="(https://reality\.idnes\.cz/detail/[^"]+/([0-9a-f]{20,})/?)"')
_DISP = re.compile(r"(\d\+(?:kk|\d))", re.I)
_AREA = re.compile(r"(?<![\d+])(\d[\d\s ]*?)\s*m²")
_IMG = re.compile(r'data-src="(https://sta-reality[^"]+)"')


class Chyba(RuntimeError):
    """Stránku se nepodařilo načíst (na rozdíl od 404 = konec výpisu)."""


def _fetch(url, pokus=1):
    """Vrátí HTML, None pro 404 (konec výpisu), jinak po 4 pokusech vyhodí Chyba."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except http.client.IncompleteRead as e:
        # iDNES občas useknou odpověď, přijatá část bývá použitelná
        if len(e.partial) >= 20_000:
            html = e.partial.decode("utf-8", "replace")
        elif pokus < 4:
            time.sleep(3 * pokus)
            return _fetch(url, pokus + 1)
        else:
            raise Chyba(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if pokus < 4:
            time.sleep(5 * pokus)
            return _fetch(url, pokus + 1)
        raise Chyba(f"{url}: HTTP {e.code}")
    except Exception as e:
        if pokus < 4:
            time.sleep(5 * pokus)
            return _fetch(url, pokus + 1)
        raise Chyba(f"{url}: {e}")
    if re.search(r"<title>\s*Robot", html):
        if pokus < 4:
            time.sleep(20 * pokus)
            return _fetch(url, pokus + 1)
        raise Chyba(f"{url}: stránka pro roboty")
    return html


def _text(html):
    return re.sub(r"[\s ]+", " ", re.sub(r"<[^>]+>", " ", html.replace("&zwj;", "").replace("&nbsp;", " "))).strip()


def _karty(html):
    for blok in html.split('class="c-products__item"')[1:]:
        h = _HREF.search(blok)
        if not h:
            continue
        t = re.search(r'c-products__title">(.*?)</h2>', blok, re.S)
        info = re.search(r'c-products__info">(.*?)</p>', blok, re.S)
        cena = re.search(r'c-products__price">(.*?)</p>', blok, re.S)
        titulek = _text(t.group(1)) if t else ""
        cena_txt = _text(cena.group(1)) if cena else ""
        digits = re.sub(r"\D", "", cena_txt.split("Kč")[0]) if "Kč" in cena_txt else ""
        area = _AREA.search(titulek)
        disp = _DISP.search(titulek)
        img = _IMG.search(blok)
        yield {
            "id": h.group(2), "url": h.group(1), "nazev": titulek[:1].upper() + titulek[1:],
            "lokalita": _text(info.group(1)) if info else "",
            "cena": int(digits) if digits else None,
            "cena_text": cena_txt,
            "plocha": int(re.sub(r"\D", "", area.group(1))) if area else None,
            "dispozice": disp.group(1).lower() if disp else None,
            "img": img.group(1) if img else None,
        }


def _search_kraj(cesta, kraj):
    out, ids, chyb = [], set(), 0
    for page in range(MAX_PAGES):
        url = f"{ROOT}/s/{cesta}/{kraj}/" + (f"?page={page}" if page else "")
        try:
            html = _fetch(url)
        except Chyba as e:
            print("  iDNES: přeskakuji stránku,", e, flush=True)
            chyb += 1
            if chyb >= 3:
                break
            continue
        chyb = 0
        time.sleep(config.REQUEST_PAUSE)
        if html is None:
            break
        karty = list(_karty(html))
        nove = [k for k in karty if k["id"] not in ids]
        if not nove:  # za poslední stránkou iDNES vrací znovu poslední stránku
            break
        for k in nove:
            ids.add(k["id"])
            k["kraj_slug"] = kraj
            out.append(k)
    return out


def search(cesta, vlakna=2):
    """cesta např. 'prodej/byty'. Stahuje po krajích souběžně, stránky od 0 do konce."""
    out, videno = [], set()
    with ThreadPoolExecutor(vlakna) as ex:
        for vysledek in ex.map(lambda k: _search_kraj(cesta, k), KRAJE):
            for k in vysledek:
                if k["id"] not in videno:
                    videno.add(k["id"])
                    out.append(k)
    return out


def detail(url):
    """Vrátí (užitná plocha, popis) z detailu inzerátu."""
    try:
        html = _fetch(url) or ""
    except Chyba:
        html = ""
    i = html.find('class="b-desc')
    popis = _text(html[i:i + 15000].split("</div>")[0]) if i >= 0 else ""
    j = html.find('class="b-definition')
    m = re.search(r"Užitná plocha ([\d ]+) m", _text(html[j:j + 8000])) if j >= 0 else None
    plocha = int(re.sub(r"\D", "", m.group(1))) if m else None
    return plocha, popis


def obec_z_lokality(lokalita, obce):
    """'Revoluční, Praha 1 - Nové Město' -> 'Praha'; vrací název obce z obce5000 nebo None."""
    lok = re.sub(r",?\s*okres\s.*$", "", lokalita, flags=re.I)
    for cast in reversed([c.strip() for c in lok.split(",")]):
        kandidati = [cast, cast.split(" - ")[0].strip(), re.sub(r"\s+\d+$", "", cast.split(" - ")[0].strip())]
        for k in kandidati:
            if k in obce:
                return k
    return None
