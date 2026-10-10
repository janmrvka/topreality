"""Jednou ročně: obnoví data/obce5000.json z tabulky ČSÚ „Počet obyvatel v obcích“ (xlsx).

  pip install openpyxl
  python obce.py cesta/k/souboru.xlsx
"""
import json
import sys
from pathlib import Path

import openpyxl

wb = openpyxl.load_workbook(sys.argv[1], read_only=True)
okres, obce = None, []
for r in wb.worksheets[0].iter_rows(values_only=True):
    if isinstance(r[0], str) and r[0].startswith("Okres "):
        okres = r[0][6:].strip()
        continue
    if isinstance(r[1], int) and isinstance(r[3], int):
        if r[2] == "Praha":
            okres = "Praha"
        if r[3] >= 5000:
            obce.append({"kod": r[1], "obec": r[2].strip(), "okres": okres, "obyvatel": r[3]})
Path(__file__).with_name("data").joinpath("obce5000.json").write_text(json.dumps(obce, ensure_ascii=False, indent=0))
print(len(obce), "obcí")
