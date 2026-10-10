"""Čtení počtu bytů a celkové plochy bytů z textu inzerátu činžovního domu."""
import re
CISLOVKY = {"dva": 2, "dvě": 2, "tři": 3, "čtyři": 4, "pět": 5, "šest": 6, "sedm": 7, "osm": 8, "devět": 9, "deset": 10,
            "jedenáct": 11, "dvanáct": 12, "třináct": 13, "čtrnáct": 14, "patnáct": 15, "šestnáct": 16,
            "sedmnáct": 17, "osmnáct": 18, "devatenáct": 19, "dvacet": 20}
_N = r"(\d{1,3}|" + "|".join(CISLOVKY) + r")"
POCET = [
    re.compile(_N + r"\s*(?:x\s*)?(?:samostatn\w+\s+|menších\s+|nájemních\s+|bytových\s+)?(?:bytov\w+\s+jednot\w*|bytů|byty|bj\b|b\.j\.)", re.I),
    re.compile(r"(?:počet|celkem)\s+(?:bytů|bytových jednotek|bj)\s*:?\s*" + _N, re.I),
    re.compile(r"(?:bytů|bytových jednotek)\s*:\s*" + _N, re.I),
]
PLOCHA_BYTU = [
    # "byty ... o celkové výměře 400 m²", "bytové jednotky o celkové ploše 520 m²"
    re.compile(r"(?<!ne)\b(?:byty|bytů|bytov\w+ jednot\w+)[^.]{0,80}?celkov\w+\s+(?:výměř\w*|ploš\w*|plo\w*)[^.\d]{0,15}(\d{2,4})\s*m", re.I),
    # "celková (užitná) plocha bytů 400 m²"
    re.compile(r"celkov\w+\s+(?:užitn\w+\s+|podlahov\w+\s+)?(?:plocha|výměra)\s+(?:všech\s+)?(?:bytů|bytových jednotek)[^.\d]{0,15}(\d{2,4})\s*m", re.I),
    # "400 m² bytové plochy", "bytová plocha 400 m²"
    re.compile(r"(\d{2,4})\s*m²?\s*(?:bytové|obytné)\s+plochy", re.I),
    re.compile(r"(?:bytová|obytná)\s+plocha[^.\d]{0,20}(\d{2,4})\s*m", re.I),
]
# plánované byty (projekt, rozdělení, možnost) nejsou byty, které dům dnes má
PLAN = re.compile(r"vybudov|návrh|navrž|projekt|možnost|lze|potenci|rozdělen|přestavb|studi|výstavb|vzniknout|vznik", re.I)

def _int(t):
    t = t.lower()
    return CISLOVKY.get(t) or int(re.sub(r"\D", "", t))

def pocet_bytu(popis):
    t = re.sub(r"\s+", " ", popis or "")
    for r in POCET:
        for m in r.finditer(t):
            n = _int(m.group(1))
            pred = t[max(0, m.start() - 70):m.start()]
            if 2 <= n <= 120 and not re.search(r"\d\+(kk|\d)\s*$", pred[-6:]) and not PLAN.search(pred):
                return n, t[max(0, m.start()-40):m.end()+20]
    return None, None

def plocha_bytu(popis, celkem):
    t = re.sub(r"\s+", " ", popis or "")
    for r in PLOCHA_BYTU:
        for m in r.finditer(t):
            v = int(re.sub(r"\D", "", m.group(1)))
            if PLAN.search(t[max(0, m.start() - 80):m.start()]):
                continue
            if 40 <= v and (not celkem or v <= celkem):
                return v, t[max(0, m.start()-30):m.end()+10]
    return None, None
