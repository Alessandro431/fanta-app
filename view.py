"""Vista SOLO LETTURA dei blocchi per i partecipanti.
Legge il campionato pubblicato in `campionato_pubblico.json` (esportato dal back-office e
committato nel repo) e mostra i blocchi per ruolo con Qt.A e FVM. Nessun controllo di modifica.
Avvio:  streamlit run view.py
"""
import json
import os

import pandas as pd
import streamlit as st

LISTONE_CSV = "listone_fantacalcio_2026_2027.csv"
FILE_PUBBLICO = "campionato_pubblico.json"
NOME_RUOLO = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}

st.set_page_config(page_title="Fantacalcio - Blocchi (vista)", layout="wide")

COLONNE = {
    "#": st.column_config.NumberColumn("#", help="Posizione per FVM nel proprio ruolo (1 = più alto).", width="small"),
    "Qt.A": st.column_config.NumberColumn("Qt.A", help="Quotazione attuale (crediti di listino)."),
    "FVM": st.column_config.NumberColumn("FVM", help="Fantavalore di Mercato (1-1000): quanto è conteso all'asta."),
}


@st.cache_data
def carica_listone():
    if not os.path.exists(LISTONE_CSV):
        return None
    df = pd.read_csv(LISTONE_CSV)
    df["Label"] = df["Nome"] + " (" + df["Squadra"] + ")"
    if "Fuori" not in df.columns:
        df["Fuori"] = 0
    df["Fuori"] = df["Fuori"].fillna(0).astype(int)
    df = df.sort_values(["FVM", "Qt.A"], ascending=False).reset_index(drop=True)
    attivi = df[df["Fuori"] == 0]
    df["#"] = attivi.groupby("R").cumcount() + 1
    df["#"] = df["#"].astype("Int64")
    return df


@st.cache_data
def carica_pubblico():
    if not os.path.exists(FILE_PUBBLICO):
        return None
    with open(FILE_PUBBLICO, encoding="utf-8") as f:
        return json.load(f)


df = carica_listone()
dati = carica_pubblico()

if df is None or dati is None:
    st.error("Dati non disponibili. Il campionato non è ancora stato pubblicato.")
    st.stop()

blocchi = dati["blocchi"]
rinomine = dati.get("rinomine", {})
# applica gli eventuali nomi corretti dal back-office
if rinomine:
    df = df.copy()
    df["Nome"] = df.apply(lambda r: rinomine.get(r["Label"], r["Nome"]), axis=1)
    df["Label"] = df["Nome"] + " (" + df["Squadra"] + ")"

st.title("🏆 Fanta-Family Blocchi")
st.markdown(
    "- **Qt.A** = quotazione attuale del giocatore (crediti di listino)\n"
    "- **FVM** = Fantavalore di Mercato: quanto il giocatore è conteso all'asta (scala 1-1000)\n"
    "- 👉 Se lo schermo è piccolo, le schede dei ruoli qui sotto (Portieri, Difensori, "
    "Centrocampisti, Attaccanti) sono **scorrevoli lateralmente**: trascina o usa la rotellina per vederle tutte."
)

ruoli_presenti = [r for r in NOME_RUOLO if r in blocchi]
tabs = st.tabs([f"{NOME_RUOLO[r]} ({len(blocchi[r])} blocchi)" for r in ruoli_presenti])

# Qt.A / FVM per etichetta dal listone (per arricchire i blocchi dove il giocatore è presente)
val_per_label = df.set_index("Label")[["Qt.A", "FVM"]].to_dict("index")


def scomponi(label):
    """Da 'Nome (SQ)' ricava (Nome, Squadra); la squadra è sempre nell'etichetta del blocco,
    così anche i giocatori entrati dopo (non presenti nel CSV) mostrano nome e squadra."""
    if label.endswith(")") and " (" in label:
        nome, sq = label.rsplit(" (", 1)
        return nome, sq[:-1]
    return label, ""


for tab, ruolo in zip(tabs, ruoli_presenti):
    with tab:
        colonne = st.columns(2)
        for i, gruppo in enumerate(blocchi[ruolo]):
            with colonne[i % 2]:
                with st.container(border=True):
                    st.markdown(f"**Blocco {ruolo}{i + 1}** — {len(gruppo)} giocatori")
                    righe = []
                    for label in gruppo:  # ordine come nel blocco
                        nome, sq = scomponi(label)
                        v = val_per_label.get(label, {})
                        righe.append({"Nome": nome, "Squadra": sq,
                                      "Qt.A": v.get("Qt.A"), "FVM": v.get("FVM")})
                    sub = pd.DataFrame(righe, columns=["Nome", "Squadra", "Qt.A", "FVM"])
                    st.dataframe(sub, hide_index=True, width="stretch", column_config=COLONNE)
                    if not sub.empty:
                        conteggio = sub["Squadra"].value_counts()
                        fvm_tot = int(sub["FVM"].fillna(0).sum())
                        st.caption("Squadre: " + " · ".join(f"{sq} ×{n}" for sq, n in conteggio.items())
                                   + f"  ·  FVM totale: {fvm_tot}")
