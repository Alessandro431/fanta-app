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

st.title("🏆 Fanta-Family Rose")
st.markdown(
    "- **Qt.A** = quotazione attuale del giocatore (crediti di listino)\n"
    "- **FVM** = Fantavalore di Mercato: quanto il giocatore è conteso all'asta (scala 1-1000)\n"
    "- 👉 Scegli un partecipante per vedere la sua rosa completa, divisa per ruolo."
)

# Rose: ogni partecipante ha un blocco per ruolo (P, D, C, A)
ROSE = {
    "Fabio": ("P1", "D1", "C3", "A10"),
    "Marco": ("P4", "D2", "C2", "A4"),
    "Leo": ("P5", "D10", "C10", "A3"),
    "Guido": ("P3", "D6", "C9", "A2"),
    "Arianna": ("P7", "D5", "C7", "A6"),
    "Paola": ("P6", "D3", "C6", "A8"),
    "Alex": ("P8", "D9", "C4", "A1"),
    "Giulia": ("P10", "D7", "C1", "A7"),
    "Francy": ("P2", "D8", "C5", "A9"),
    "Marty": ("P9", "D4", "C8", "A5"),
}

# Nome della fantasquadra registrata su Leghe Fantacalcio (per l'import CSV automatico)
NOME_LEGA = {
    "Alex": "Real Essandro",
    "Fabio": "Divano Kiev",
    "Paola": "NON CI RESTA CHE PJANIC",
    "Giulia": "San Diego",
    "Guido": "Guienz",
    "Marty": "In mano a Christensen",
    "Francy": "FC bellinGAS",
    "Leo": "fenice academy",
    "Arianna": "Tanto pe Kante",
    "Marco": "Marco",  # squadra non ancora registrata: associare a mano in fase di import
}

# Qt.A / FVM per etichetta dal listone; in fallback per solo nome (se la squadra nel blocco differisce)
val_per_label = df.set_index("Label")[["Qt.A", "FVM"]].to_dict("index")
_conta_nome = df["Nome"].value_counts()
_univoci = df[df["Nome"].map(_conta_nome) == 1]  # solo nomi univoci, per evitare omonimi
val_per_nome = _univoci.set_index("Nome")[["Qt.A", "FVM"]].to_dict("index")


def scomponi(label):
    """Da 'Nome (SQ)' ricava (Nome, Squadra); la squadra è sempre nell'etichetta del blocco,
    così anche i giocatori entrati dopo (non presenti nel CSV) mostrano nome e squadra."""
    if label.endswith(")") and " (" in label:
        nome, sq = label.rsplit(" (", 1)
        return nome, sq[:-1]
    return label, ""


def giocatori_blocco(codice):
    """Dato un codice tipo 'D6' ritorna le righe (Ruolo, Nome, Squadra, Qt.A, FVM) del blocco."""
    ruolo, idx = codice[0], int(codice[1:]) - 1
    righe = []
    for label in blocchi.get(ruolo, [[]] * (idx + 1))[idx]:
        nome, sq = scomponi(label)
        v = val_per_label.get(label) or val_per_nome.get(nome, {})
        righe.append({"Ruolo": ruolo, "Nome": nome, "Squadra": sq,
                      "Qt.A": v.get("Qt.A"), "FVM": v.get("FVM")})
    return righe


rose_calc = []
for nome_p, codici in ROSE.items():
    righe = [r for c in codici for r in giocatori_blocco(c)]
    dfp = pd.DataFrame(righe, columns=["Ruolo", "Nome", "Squadra", "Qt.A", "FVM"])
    rose_calc.append((nome_p, codici, dfp, int(dfp["FVM"].fillna(0).sum()), int(dfp["Qt.A"].fillna(0).sum())))
rose_calc.sort(key=lambda t: t[3], reverse=True)

INTESTAZIONE = "Fantasquadra;Calciatore;Ruolo;Prezzo"


def righe_rosa(nome_p, dfr):
    """Righe 'Fantasquadra;Calciatore;Ruolo;Prezzo' col nome squadra registrato su Leghe (Prezzo=1)."""
    squadra = NOME_LEGA.get(nome_p, nome_p)
    return [f"{squadra};{r.Nome};{r.Ruolo};1" for r in dfr.itertuples()]


def csv_tutte(rose):
    righe = [INTESTAZIONE]
    for nome_p, _cod, dfr, *_ in rose:
        righe += righe_rosa(nome_p, dfr)
    return ("\r\n".join(righe) + "\r\n").encode("utf-8")


def csv_singola(nome_p, dfr):
    return ("\r\n".join([INTESTAZIONE] + righe_rosa(nome_p, dfr)) + "\r\n").encode("utf-8")


def xlsx_tutte(rose):
    """Stesse informazioni in formato Excel (spesso più affidabile all'import di Leghe)."""
    import io
    righe = []
    for nome_p, _cod, dfr, *_ in rose:
        squadra = NOME_LEGA.get(nome_p, nome_p)
        for r in dfr.itertuples():
            righe.append({"Fantasquadra": squadra, "Calciatore": r.Nome, "Ruolo": r.Ruolo, "Prezzo": 1})
    buf = io.BytesIO()
    pd.DataFrame(righe).to_excel(buf, index=False, sheet_name="Rose")
    return buf.getvalue()


nomi_ordinati = [n for n, *_ in rose_calc]
cd1, cd2 = st.columns(2)
cd1.download_button("⬇️ Tutte le rose — CSV",
                    data=csv_tutte(rose_calc), file_name="rose_lega.csv", mime="text/csv",
                    width="stretch",
                    help="Un solo file con tutte le squadre. Tracciato Calciatore;Fantasquadra;Prezzo (Prezzo=1).")
cd1.download_button("⬇️ Tutte le rose — Excel (.xlsx)",
                    data=xlsx_tutte(rose_calc), file_name="rose_lega.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                    help="Formato Excel: se il CSV dà 'file non riconosciuto', prova con questo.")

scelto = st.selectbox("Mostra la rosa di", nomi_ordinati, key="rosa_scelta")
nome_p, codici, dfp, fvm, qta = next(t for t in rose_calc if t[0] == scelto)
cd2.download_button(f"⬇️ Scarica solo la rosa di {scelto} (CSV)",
                    data=csv_singola(nome_p, dfp),
                    file_name=f"rosa_{scelto.lower()}.csv", mime="text/csv", width="stretch")
st.markdown(f"### 🧑 {nome_p} — FVM **{fvm}** · Qt.A **{qta}** · {len(dfp)} giocatori")
ICONA = {"P": "🧤 Portieri", "D": "🛡️ Difensori", "C": "🎯 Centrocampisti", "A": "⚽ Attaccanti"}
colonne = st.columns(4)
for col, ruolo in zip(colonne, "PDCA"):
    with col:
        parte = (dfp[dfp["Ruolo"] == ruolo][["Nome", "Squadra", "Qt.A", "FVM"]]
                 .sort_values("FVM", ascending=False))
        st.markdown(f"**{ICONA[ruolo]} ({len(parte)})**")
        st.dataframe(parte, hide_index=True, width="stretch",
                     height=38 + 35 * max(len(parte), 1),  # niente scroll interno
                     column_config=COLONNE)

with st.expander("📊 Classifica rose per FVM totale"):
    st.dataframe(pd.DataFrame([{"Partecipante": n, "Blocchi": " · ".join(c),
                                "Giocatori": len(d), "FVM totale": fvm, "Qt.A totale": qta}
                               for n, c, d, fvm, qta in rose_calc]),
                 hide_index=True, width="stretch")
