"""Nastavení modelu. Měň tady, skript si to přečte při každém běhu."""

SAZBA = 0.053          # roční úroková sazba hypotéky
SPLATNOST_LET = 30
LTV = 1.0              # 100 % financování z kupní ceny
CENA_MAX = 30_000_000  # Kč
CASHFLOW_MIN = -5_000  # Kč/měsíc, do dashboardu jdou nabídky s cashflow >= této hodnoty
MIN_OBYVATEL = 5_000

# Kolik nabídek pronájmu musí v obci být, aby byl odhad nájmu "vysoká" jistota
VZOREK_VYSOKA = 8
VZOREK_STREDNI = 3

# Poměr pronajímatelné plochy u činžáku, když nájem odhadujeme z plochy
CINZAK_PODIL_PLOCHY = 1.0

REQUEST_PAUSE = 0.6    # s mezi dotazy na portál

# Hrubý výnos nad touto hranicí je skoro jistě chyba dat (plocha, cena, ruina) -> v dashboardu skryté
VYNOS_PODEZRELY = 0.15
