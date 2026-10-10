# Cashflow nemovitostí

Denně projde Sreality, Bezrealitky a iDNES Reality a najde **byty a činžovní domy** v obcích nad 5 000 obyvatel,
které při 100% financování vychází na nulové nebo kladné cashflow (do dashboardu jdou i nabídky do −5 000 Kč).

**Cashflow = odhad měsíčního nájmu − anuitní splátka** (5,3 %, 30 let, 100 % kupní ceny). Žádné další náklady.

- **Nájem bytu**: medián Kč/m² z aktuálních pronájmů stejné dispozice v obci (vzorek z posledních 14 dní ze všech tří portálů).
  Málo dat v obci → obec bez rozlišení dispozice → okres → kraj, s jistotou vysoká / střední / nízká.
- **Nájem činžáku**: částka nebo výnos uvedený v textu inzerátu (s citací), jinak hrubý odhad z užitné plochy (vždy „nízká“).
- Nabídky s hrubým výnosem nad 15 % jsou v dashboardu skryté jako podezřelé (chybná plocha, ruina).

## Nastavení
Vše v `config.py` (sazba, splatnost, cenový strop, hranice cashflow, min. počet obyvatel).

## Spuštění
```bash
python3 run.py --plny   # všechny portály + pronájmy, 30–70 min
python3 run.py          # rychlý běh: prodeje Sreality + Bezrealitky, nájmy a iDNES z minula, ~5 min
```
Výstup: `dashboard/data.json`, dashboard je `dashboard/index.html` (potřebuje web server, např. `python3 -m http.server -d dashboard`).

## Automatika (GitHub Actions)
`.github/workflows/beh.yml`: plný běh denně ve 4:17, rychlý v 7, 10, 13, 16, 19 a 22 h (letní čas).
Databáze se mezi běhy ukládá do releasu `stav`, dashboard se nasazuje na GitHub Pages.

## Obce
`data/obce5000.json` je z ČSÚ (stav k 1. 1. 2025). Obnova jednou ročně: `python3 obce.py soubor.xlsx`.
