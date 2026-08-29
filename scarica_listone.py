"""Scarica il listone quotazioni Fantacalcio (stagione corrente) dalla pagina pubblica
https://www.fantacalcio.it/quotazioni-fantacalcio e lo salva in Excel e CSV."""
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

URL = "https://www.fantacalcio.it/quotazioni-fantacalcio"
URL_TRASFERIMENTI = "https://www.fantacalcio.it/calciomercato/trasferimenti-ufficiali"
SQUADRE_SERIE_A = {"Atalanta", "Bologna", "Cagliari", "Como", "Fiorentina", "Frosinone", "Genoa", "Inter", "Juventus",
                   "Lazio", "Lecce", "Milan", "Monza", "Napoli", "Parma", "Roma", "Sassuolo", "Torino", "Udinese", "Venezia"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def scarica_trasferimenti():
    """Ritorna {id giocatore: "Da → A (tipo)"} dall'elenco dei trasferimenti ufficiali.
    Per chi ha lasciato la Serie A tiene il trasferimento verso l'estero/svincolo; per gli altri l'ultimo arrivo."""
    try:
        r = requests.get(URL_TRASFERIMENTI, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception:  # noqa: BLE001 - i trasferimenti sono un extra, il listone non deve fallire
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    out = {}
    for li in soup.select("li.transfer[id]"):
        nome = li.select_one(".header .name")
        desc = li.select_one(".header .desc")
        da = li.select_one(".team-left .name")
        a = li.select_one(".team-joined .name")
        if not (nome and da and a):
            continue
        da, a = da.get_text(strip=True), a.get_text(strip=True)
        voce = f"{da} -> {a}" + (f" ({desc.get_text(strip=True)})" if desc else "")
        pid = li["id"]
        # priorita': uscita dalla Serie A > arrivo in Serie A > altro
        prio = 2 if (da in SQUADRE_SERIE_A and a not in SQUADRE_SERIE_A) else 1 if a in SQUADRE_SERIE_A else 0
        if pid not in out or prio >= out[pid][0]:
            out[pid] = (prio, voce)
    return {pid: v for pid, (_, v) in out.items()}


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
    trasf = scarica_trasferimenti()
    df["Trasferimento"] = df["Id"].map(trasf).fillna("")
    return df

if __name__ == "__main__":
    import os, shutil
    df = scarica_listone()
    if os.path.exists("listone_fantacalcio_2026_2027.csv"):  # conserva la versione precedente per il confronto In/Out
        shutil.copyfile("listone_fantacalcio_2026_2027.csv", "listone_precedente.csv")
    df.to_excel("listone_fantacalcio_2026_2027.xlsx", index=False)
    df.to_csv("listone_fantacalcio_2026_2027.csv", index=False)
    print(f"{len(df)} giocatori, {df['Squadra'].nunique()} squadre, {int(df['Fuori'].sum())} fuori dalla Serie A (asterisco)")
    print(df["R"].value_counts().to_dict())
    print(df.head(10).to_string())
