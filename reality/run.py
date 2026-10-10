"""Běh: stáhne nabídky, odhadne nájem, spočítá cashflow a zapíše dashboard/data.json.

  python run.py --plny    všechny portály vč. pronájmů a iDNES (1× denně, ~30–40 min)
  python run.py           rychlý běh: prodeje ze Srealit a Bezrealitek, nájmy z DB (~3 min)
"""
import argparse
import json
import re
import sqlite3
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import bezrealitky
import config
import idnes
import sreality

ROOT = Path(__file__).parent
DB = ROOT / "data" / "reality.db"
OUT = ROOT / "dashboard" / "data.json"


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


# ---------- obce ----------

def nacti_obce():
    obce = json.loads((ROOT / "data" / "obce5000.json").read_text())
    return {o["obec"]: o for o in obce if o["obyvatel"] >= config.MIN_OBYVATEL}


# ---------- databáze ----------

def db():
    con = sqlite3.connect(DB)
    con.executescript("""
    create table if not exists nabidky(
        id text primary key, zdroj text, typ text,
        first_seen text, last_seen text,
        cena integer, cena_puvodni integer, cena_zmena text);
    create table if not exists detaily(
        id text primary key, fetched text, plocha integer, popis text);
    create table if not exists najmy(
        id text primary key, zdroj text, obec text, okres text, kraj text,
        dispozice text, plocha integer, najem integer, last_seen text);
    create table if not exists meta(k text primary key, v text);
    """)
    return con


def meta_get(con, k, default=None):
    row = con.execute("select v from meta where k=?", (k,)).fetchone()
    return json.loads(row[0]) if row else default


def meta_set(con, k, v):
    con.execute("insert or replace into meta values(?,?)", (k, json.dumps(v, ensure_ascii=False)))


# ---------- splátka ----------

def splatka(jistina):
    r = config.SAZBA / 12
    n = config.SPLATNOST_LET * 12
    return jistina * r / (1 - (1 + r) ** -n)


# ---------- nájmy ----------

def statistiky_najmu(rows):
    """Medián Kč/m² podle (obec, dispozice), (obec), (okres, dispozice), (okres), (kraj, dispozice)."""
    k = defaultdict(list)
    for obec, okres, kraj, d, plocha, najem in rows:
        if not plocha or plocha < 12 or not najem or najem < 2000:
            continue
        m2 = najem / plocha
        if not 60 <= m2 <= 1200:
            continue
        k[("obec", obec, d)].append(m2)
        k[("obec", obec, "*")].append(m2)
        if okres:
            k[("okres", okres, d)].append(m2)
            k[("okres", okres, "*")].append(m2)
        if kraj:
            k[("kraj", kraj, d)].append(m2)
    return {key: (statistics.median(v), len(v)) for key, v in k.items()}


def odhad_m2(stat, obec, okres, kraj, disp):
    """Vrátí (Kč/m², jistota, popis vzorku)."""
    pokusy = [
        (("obec", obec, disp), config.VZOREK_VYSOKA, "vysoká", f"{disp} v obci"),
        (("obec", obec, disp), config.VZOREK_STREDNI, "střední", f"{disp} v obci"),
        (("obec", obec, "*"), config.VZOREK_VYSOKA, "střední", "všechny byty v obci"),
        (("okres", okres, disp), config.VZOREK_STREDNI, "nízká", f"{disp} v okrese"),
        (("okres", okres, "*"), config.VZOREK_STREDNI, "nízká", "všechny byty v okrese"),
        (("kraj", kraj, disp), config.VZOREK_STREDNI, "nízká", f"{disp} v kraji"),
    ]
    for key, minimum, jistota, popis in pokusy:
        if key in stat and stat[key][1] >= minimum:
            m2, n = stat[key]
            return m2, jistota, f"{popis} (n={n})"
    return None, None, None


# ---------- nájem uvedený v inzerátu činžáku ----------

CASTKA = re.compile(
    r"(\d{1,3}(?:[ . ]\d{3})+|\d+(?:[,.]\d+)?)\s*(mil\.?|milion\w*|tis\.?|tisíc\w*)?\s*(?:kč|,-|czk)",
    re.I)
VYNOS = re.compile(r"(výnos\w*|výnosnost\w*|yield)[^.%\d]{0,40}?(\d{1,2}(?:[,.]\d{1,2})?)\s*%", re.I)


def _cislo(txt, nasobek):
    txt = txt.replace(" ", " ")
    if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", txt):
        v = float(re.sub(r"[ .]", "", txt))
    else:
        v = float(txt.replace(",", "."))
    if nasobek:
        v *= 1_000_000 if nasobek.lower().startswith("mil") else 1_000
    return v


def najem_z_popisu(popis, cena):
    """Zkusí najít v textu inzerátu měsíční nájem. Vrátí (Kč/měsíc, citace) nebo (None, None)."""
    if not popis:
        return None, None
    t = re.sub(r"\s+", " ", popis)
    nizky, vysoky = cena * 0.02 / 12, cena * 0.20 / 12  # rozumný hrubý výnos 2–20 %
    for m in CASTKA.finditer(t):
        pred = t[max(0, m.start() - 90):m.start()].lower()
        po = t[m.end():m.end() + 25].lower()
        okoli = pred + " " + po
        if not re.search(r"nájem|nájm|příjem|příjm|výnos|inkas", okoli):
            continue
        # potenciální nájem po rekonstrukci ani nájem jednoho bytu nechceme
        if re.search(r"potenci|po rekonstrukc|možn|orientační nájem|\d\+(kk|\d)", pred[-60:]):
            continue
        try:
            v = _cislo(m.group(1), m.group(2))
        except ValueError:
            continue
        if re.search(r"ročn|za rok|/ ?rok|p\.? ?a\.|rok", okoli):
            mesicne = v / 12
        elif re.search(r"měsíč|měsíc|/ ?měs", okoli):
            mesicne = v
        else:
            continue
        if nizky <= mesicne <= vysoky:
            return round(mesicne), t[max(0, m.start() - 70):m.end() + 15].strip()
    m = VYNOS.search(t)
    if m:
        y = float(m.group(2).replace(",", ".")) / 100
        if 0.02 <= y <= 0.20:
            return round(cena * y / 12), t[max(0, m.start() - 30):m.end() + 10].strip()
    return None, None


# ---------- sběr pronájmů ----------

def sber_najmu(con, obce, okres_kraj, dnes):
    rows = []

    log("Sreality: pronájmy bytů…")
    for r in sreality.search(1, 2):
        if r["price_unit_cb"]["name"] != "za měsíc":
            continue
        loc = r["locality"]
        okres_kraj[loc.get("district")] = loc.get("region")
        rows.append((f"sreality:{r['hash_id']}", "sreality", loc.get("city"), loc.get("district"), loc.get("region"),
                     r["category_sub_cb"]["name"], sreality.plocha(r), int(r.get("price_czk") or 0)))
    log(f"  celkem {len(rows)}")

    log("Bezrealitky: pronájmy bytů…")
    n = len(rows)
    for r in bezrealitky.search("PRONAJEM"):
        obec = r.get("city")
        okres = obce[obec]["okres"] if obec in obce else None
        rows.append((f"bezrealitky:{r['id']}", "bezrealitky", obec, okres, okres_kraj.get(okres),
                     bezrealitky.dispozice(r.get("disposition")), r.get("surface"), int(r.get("price") or 0)))
    log(f"  +{len(rows) - n}")

    log("iDNES: pronájmy bytů…")
    n = len(rows)
    for k in idnes.search("pronajem/byty"):
        obec = idnes.obec_z_lokality(k["lokalita"], obce)
        if not obec or not k["cena"] or "měs" not in k["cena_text"]:
            continue
        okres = obce[obec]["okres"]
        rows.append((f"idnes:{k['id']}", "idnes", obec, okres, okres_kraj.get(okres),
                     k["dispozice"] or "Atypický", k["plocha"], k["cena"]))
    log(f"  +{len(rows) - n}")

    # stejný byt na více portálech se do mediánu započte jednou
    videno, unik = set(), []
    for row in rows:
        klic = (row[2], row[6], row[7])
        if klic in videno:
            continue
        videno.add(klic)
        unik.append(row)
    con.executemany("insert or replace into najmy values(?,?,?,?,?,?,?,?,?)", [(*r, dnes) for r in unik])
    con.commit()
    log(f"Pronájmy: {len(unik)} unikátních (z {len(rows)})")


# ---------- sběr prodejů ----------

IDNES_PRODEJ = (("byt", "prodej/byty"), ("činžák", "prodej/komercni-nemovitosti/najemni-domy"))

def sber_prodeju(obce, okres_kraj, plny):
    """Vrátí seznam nabídek ve společném formátu (pořadí = priorita při slučování duplicit)."""
    out = []

    log("Sreality: prodej bytů…")
    byty = sreality.search(1, 1, price_to=config.CENA_MAX)
    log("Sreality: prodej činžovních domů…")
    cinzaky = sreality.search(4, 1, sub_cb=38, price_to=config.CENA_MAX)
    for typ, seznam in (("byt", byty), ("činžák", cinzaky)):
        for r in seznam:
            loc = r["locality"]
            okres_kraj[loc.get("district")] = loc.get("region")
            if loc.get("city") not in obce or r["price_unit_cb"]["name"] != "za nemovitost":
                continue
            out.append({
                "id": f"sreality:{r['hash_id']}", "zdroj": "Sreality", "typ": typ,
                "nazev": r.get("advert_name", "").replace(" ", " "),
                "obec": loc.get("city"), "okres": loc.get("district"), "kraj": loc.get("region"),
                "ulice": loc.get("street"), "dispozice": r["category_sub_cb"]["name"] if typ == "byt" else None,
                "plocha": sreality.plocha(r), "cena": int(r.get("price_czk") or 0),
                "url": sreality.url(r), "img": sreality.obrazek(r),
                "lat": loc.get("gps_lat"), "lon": loc.get("gps_lon"),
                "_detail": (lambda h=r["hash_id"]: _sreality_detail(h)) if typ == "činžák" else None,
            })
    log(f"  {len(byty)} bytů, {len(cinzaky)} činžáků, z toho v obcích 5000+: {len(out)}")

    log("Bezrealitky: prodej bytů…")
    n = len(out)
    for r in bezrealitky.search("PRODEJ"):
        obec = r.get("city")
        if obec not in obce:
            continue
        okres = obce[obec]["okres"]
        gps = r.get("gps") or {}
        disp = bezrealitky.dispozice(r.get("disposition"))
        out.append({
            "id": f"bezrealitky:{r['id']}", "zdroj": "Bezrealitky", "typ": "byt",
            "nazev": f"Prodej bytu {disp} {r.get('surface') or ''} m²",
            "obec": obec, "okres": okres, "kraj": okres_kraj.get(okres),
            "ulice": (r.get("address") or "").split(",")[0], "dispozice": disp,
            "plocha": r.get("surface"), "cena": int(r.get("price") or 0),
            "url": bezrealitky.url(r), "img": (r.get("mainImage") or {}).get("url"),
            "lat": gps.get("lat"), "lon": gps.get("lng"), "_detail": None,
        })
    log(f"  v obcích 5000+: {len(out) - n}")

    # iDNES je pomalý (~1 h), stahuje se jen v plném běhu; rychlý běh použije uložený výpis
    cache = ROOT / "data" / "idnes_cache.json"
    if plny or not cache.exists():
        vypis = {typ: idnes.search(cesta) for typ, cesta in IDNES_PRODEJ}
        cache.write_text(json.dumps(vypis, ensure_ascii=False))
    else:
        vypis = json.loads(cache.read_text())
    for typ, cesta in IDNES_PRODEJ:
        log(f"iDNES: {cesta}" + ("" if plny else " (z mezipaměti)") + "…")
        n = len(out)
        for k in vypis[typ]:
            obec = idnes.obec_z_lokality(k["lokalita"], obce)
            if not obec or not k["cena"]:
                continue
            okres = obce[obec]["okres"]
            out.append({
                "id": f"idnes:{k['id']}", "zdroj": "iDNES", "typ": typ, "nazev": k["nazev"],
                "obec": obec, "okres": okres, "kraj": okres_kraj.get(okres),
                "ulice": k["lokalita"].split(",")[0] if "," in k["lokalita"] else None,
                "dispozice": (k["dispozice"] or "Atypický") if typ == "byt" else None,
                "plocha": k["plocha"], "cena": k["cena"], "url": k["url"], "img": k["img"],
                "lat": None, "lon": None,
                "_detail": (lambda u=k["url"]: idnes.detail(u)) if typ == "činžák" else None,
            })
        log(f"  v obcích 5000+: {len(out) - n}")
    return out


def _sreality_detail(hash_id):
    d = sreality.detail(hash_id)
    up = d.get("usable_area") or d.get("floor_area")
    return (int(up) if up else None), (d.get("advert_description") or "")


# ---------- hlavní běh ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plny", action="store_true", help="i pronájmy a iDNES")
    args = ap.parse_args()

    t0 = time.time()
    dnes = datetime.now().strftime("%Y-%m-%d %H:%M")
    obce = nacti_obce()
    con = db()
    okres_kraj = meta_get(con, "okres_kraj", {})

    if args.plny or not con.execute("select 1 from najmy limit 1").fetchone():
        sber_najmu(con, obce, okres_kraj, dnes)
    od = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    najmy = con.execute("select obec, okres, kraj, dispozice, plocha, najem from najmy where last_seen >= ?", (od,)).fetchall()
    stat = statistiky_najmu(najmy)

    nabidky = sber_prodeju(obce, okres_kraj, args.plny)
    meta_set(con, "okres_kraj", okres_kraj)

    vysledky, podle_klice = [], {}
    for x in nabidky:
        cena = x["cena"]
        if cena < 100_000 or cena > config.CENA_MAX:
            continue
        # stejná nemovitost na více portálech: nech první (Sreality > Bezrealitky > iDNES), ostatní jako odkaz
        # u činžáků se plocha mezi portály liší (užitná × celková), páruje se jen cenou
        klic = (x["typ"], x["obec"], x["plocha"] if x["typ"] == "byt" else None, round(cena, -3))
        if klic in podle_klice:
            podle_klice[klic].setdefault("dalsi", []).append({"zdroj": x["zdroj"], "url": x["url"]})
            continue

        detail_fn = x.pop("_detail")
        najem = jistota = zdroj_najmu = citace = None
        if x["typ"] == "byt":
            m2, jistota, zdroj_najmu = odhad_m2(stat, x["obec"], x["okres"], x["kraj"], x["dispozice"])
            if m2 and x["plocha"]:
                najem = round(m2 * x["plocha"])
        else:
            row = con.execute("select plocha, popis from detaily where id=?", (x["id"],)).fetchone()
            if not row:
                try:
                    row = detail_fn()
                except Exception as e:
                    log("  detail selhal", x["id"], e)
                    row = (None, "")
                time.sleep(config.REQUEST_PAUSE)
                con.execute("insert or replace into detaily values(?,?,?,?)", (x["id"], dnes, *row))
                con.commit()
            x["plocha"] = row[0] or x["plocha"]
            najem, citace = najem_z_popisu(row[1], cena)
            if najem:
                jistota, zdroj_najmu = "z inzerátu", "uvedeno v inzerátu"
            else:
                m2, jistota, zdroj_najmu = odhad_m2(stat, x["obec"], x["okres"], x["kraj"], "*")
                if m2 and x["plocha"]:
                    najem = round(m2 * x["plocha"] * config.CINZAK_PODIL_PLOCHY)
                    # u činžáku nevíme stav ani podíl bytů na ploše, odhad je vždy hrubý
                    jistota, zdroj_najmu = "nízká", "odhad z plochy × " + zdroj_najmu
        if not najem:
            continue

        spl = splatka(cena * config.LTV)
        cf = round(najem - spl)

        old = con.execute("select first_seen, cena, cena_puvodni, cena_zmena from nabidky where id=?", (x["id"],)).fetchone()
        if old:
            first_seen, cena_db, cena_puv, cena_zmena = old
            if cena != cena_db:
                cena_zmena = dnes
            con.execute("update nabidky set last_seen=?, cena=?, cena_zmena=? where id=?", (dnes, cena, cena_zmena, x["id"]))
        else:
            first_seen, cena_puv, cena_zmena = dnes, cena, None
            con.execute("insert into nabidky values(?,?,?,?,?,?,?,?)", (x["id"], x["zdroj"], x["typ"], dnes, dnes, cena, cena, None))

        if cf < config.CASHFLOW_MIN:
            continue
        x.update({
            "obyvatel": obce[x["obec"]]["obyvatel"],
            "cena_puvodni": cena_puv, "cena_zmena": cena_zmena,
            "cena_m2": round(cena / x["plocha"]) if x["plocha"] else None,
            "najem": najem, "najem_m2": round(najem / x["plocha"]) if x["plocha"] else None,
            "jistota": jistota, "najem_zdroj": zdroj_najmu, "najem_citace": citace,
            "splatka": round(spl), "cashflow": cf, "vynos": round(najem * 12 / cena * 100, 2),
            "podezrele": najem * 12 / cena > config.VYNOS_PODEZRELY,
            "first_seen": first_seen,
        })
        podle_klice[klic] = x
        vysledky.append(x)
    con.commit()

    vysledky.sort(key=lambda v: -v["cashflow"])
    OUT.parent.mkdir(exist_ok=True)
    meta = {
        "aktualizace": dnes, "plny_beh": args.plny or meta_get(con, "posledni_plny"),
        "sazba": config.SAZBA, "splatnost": config.SPLATNOST_LET, "ltv": config.LTV,
        "cena_max": config.CENA_MAX, "cashflow_min": config.CASHFLOW_MIN,
        "min_obyvatel": config.MIN_OBYVATEL, "obci": len(obce),
        "najmu_v_modelu": len(najmy), "nabidek_prodeje": len(nabidky),
        "splatka_na_milion": round(splatka(1_000_000)),
        "trvani_s": round(time.time() - t0),
    }
    if args.plny:
        meta_set(con, "posledni_plny", dnes)
        meta["plny_beh"] = dnes
    con.commit()
    OUT.write_text(json.dumps({"meta": meta, "nabidky": vysledky}, ensure_ascii=False))
    log(f"Hotovo: {len(vysledky)} nabídek s cashflow ≥ {config.CASHFLOW_MIN} Kč, {meta['trvani_s']} s")


if __name__ == "__main__":
    main()
