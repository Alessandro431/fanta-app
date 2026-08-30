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

st.title(f"🏆 {dati.get('nome', 'Campionato')} — Blocchi")
st.caption("Vista di sola lettura per i partecipanti. **Qt.A** = quotazione attuale · "
           "**FVM** = Fantavalore di Mercato (quanto è conteso all'asta).")

ruoli_presenti = [r for r in NOME_RUOLO if r in blocchi]
tabs = st.tabs([f"{NOME_RUOLO[r]} ({len(blocchi[r])} blocchi)" for r in ruoli_presenti])

for tab, ruolo in zip(tabs, ruoli_presenti):
    with tab:
        df_r = df[df["R"] == ruolo]
        colonne = st.columns(2)
        for i, gruppo in enumerate(blocchi[ruolo]):
            with colonne[i % 2]:
                with st.container(border=True):
                    st.markdown(f"**Blocco {ruolo}{i + 1}** — {len(gruppo)} giocatori")
                    sub = df_r[df_r["Label"].isin(gruppo)][["#", "Nome", "Squadra", "Qt.A", "FVM"]]
                    # mantieni l'ordine dei giocatori come nel blocco
                    if not sub.empty:
                        sub = sub.set_index("Nome").reindex(
                            [g.rsplit(" (", 1)[0] for g in gruppo]).reset_index()
                        sub = sub[["#", "Nome", "Squadra", "Qt.A", "FVM"]]
                    st.dataframe(sub, hide_index=True, width="stretch", column_config=COLONNE)
                    if not sub.empty:
                        conteggio = sub["Squadra"].value_counts()
                        st.caption("Squadre: " + " · ".join(f"{sq} ×{n}" for sq, n in conteggio.items())
                                   + f"  ·  FVM totale: {int(sub['FVM'].sum())}")
