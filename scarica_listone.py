"""Scarica il listone quotazioni Fantacalcio (stagione corrente) dalla pagina pubblica
https://www.fantacalcio.it/quotazioni-fantacalcio e lo salva in Excel e CSV."""
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

URL = "https://www.fantacalcio.it/quotazioni-fantacalcio"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def scarica_listone():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    righe = []
    for tr in soup.select("tr[data-filter-role-classic]"):
        nome = tr.select_one("th.player-name span")
        if not nome:
            continue
        link = tr.select_one("a.player-link")
        ruolo_cl = tr.select_one("span.role:not(.role-mantra)")
        ruoli_m = [s["data-value"].upper() for s in tr.select("span.role-mantra")]
        def cella(k):
            td = tr.select_one(f'[data-col-key="{k}"]')
            return td.get_text(strip=True) if td else None
        fuori = tr.select_one("span.out-of-game") is not None  # asterisco: "Non gioca più in Serie A"
        righe.append({
            "Fuori": int(fuori),
            "Id": link["href"].rstrip("/").split("/")[-1] if link else None,
            "Nome": nome.get_text(strip=True),
            "Squadra": cella("sq"),
            "R": (ruolo_cl["data-value"].upper() if ruolo_cl else None),
            "RM": ";".join(ruoli_m),
            "Qt.I": cella("c_qi"), "Qt.A": cella("c_qa"),
            "Qt.I M": cella("m_qi"), "Qt.A M": cella("m_qa"),
            "FVM": cella("c_fvm"), "FVM M": cella("m_fvm"),
        })
    df = pd.DataFrame(righe)
    for c in ["Qt.I", "Qt.A", "Qt.I M", "Qt.A M", "FVM", "FVM M"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

if __name__ == "__main__":
    df = scarica_listone()
    df.to_excel("listone_fantacalcio_2026_2027.xlsx", index=False)
    df.to_csv("listone_fantacalcio_2026_2027.csv", index=False)
    print(f"{len(df)} giocatori, {df['Squadra'].nunique()} squadre, {int(df['Fuori'].sum())} fuori dalla Serie A (asterisco)")
    print(df["R"].value_counts().to_dict())
    print(df.head(10).to_string())
