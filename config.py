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

# Podíl bytů na celkové ploše činžáku, když plocha bytů v inzerátu není (zbytek: chodby, schodiště, sklepy, nebytové prostory)
CINZAK_PODIL_PLOCHY = 0.6

REQUEST_PAUSE = 0.6    # s mezi dotazy na portál

# Hrubý výnos nad touto hranicí je skoro jistě chyba dat (plocha, cena, ruina) -> v dashboardu skryté
VYNOS_PODEZRELY = 0.15

# Kolik detailů inzerátů smí jeden běh stáhnout (zbytek se dotáhne v dalších bězích)
DETAIL_MAX_SREALITY = 1500   # datum zveřejnění bytů
DETAIL_MAX_IDNES = 40        # texty činžáků, iDNES je pomalý a brzdí
