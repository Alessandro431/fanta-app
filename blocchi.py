"""Frontend Streamlit per creare un campionato Fantacalcio a blocchi.
Per ogni ruolo ci sono 10 blocchi con un numero fisso di giocatori:
P=6, D=8, C=10, A=6. Un giocatore assegnato a un blocco sparisce dal listone.
Avvio:  streamlit run blocchi.py
"""
import json
import os
import re

import pandas as pd
import streamlit as st
from unidecode import unidecode

LISTONE_CSV = "listone_fantacalcio_2026_2027.csv"
N_BLOCCHI = 10
DIM_BLOCCO = {"P": 6, "D": 8, "C": 10, "A": 6}
NOME_RUOLO = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
SOGLIA_SQUADRA = 3  # da questo numero in su, un blocco ha "troppi" giocatori della stessa squadra
SINGOLARE = {"P": "portiere", "D": "difensore", "C": "centrocampista", "A": "attaccante"}
CARTELLA_CAMPIONATI = "campionati"

# Tooltip (mostrati passando il mouse sull'intestazione della colonna)
COLONNE = {
    "#": st.column_config.NumberColumn("#", help="Posizione fissa per FVM nel listone completo, all'interno del proprio ruolo (1 = FVM più alto del ruolo). Resta uguale in tutte le tabelle.", width="small"),
    "Qt.I": st.column_config.NumberColumn(
        "Qt.I", help="Quotazione INIZIALE: valore di listino ufficiale del giocatore a inizio stagione (crediti d'asta)."),
    "Qt.A": st.column_config.NumberColumn(
        "Qt.A", help="Quotazione ATTUALE: valore di listino aggiornato oggi da Fantacalcio.it. Sale/scende in base a forma, minutaggio e infortuni."),
    "FVM": st.column_config.NumberColumn(
        "FVM", help="Fantavalore di Mercato (scala 1-1000): quanto il giocatore è ricercato/pagato nelle aste reali. Più alto = più conteso."),
    "R": st.column_config.TextColumn("R", help="Ruolo Classic: P portiere, D difensore, C centrocampista, A attaccante."),
}
LEGENDA = ("ℹ️ **Qt.A** = quotazione attuale (crediti di listino oggi) · "
           "**FVM** = Fantavalore di Mercato, quanto è conteso all'asta (1-1000). "
           "Passa il mouse sull'intestazione delle colonne per i dettagli.")

st.set_page_config(page_title="Fantacalcio - Blocchi", layout="wide")


@st.cache_data
def carica_listone():
    if not os.path.exists(LISTONE_CSV):
        return None
    df = pd.read_csv(LISTONE_CSV)
    df["Label"] = df["Nome"] + " (" + df["Squadra"] + ")"
    df = df.sort_values(["FVM", "Qt.A"], ascending=False).reset_index(drop=True)
    df["#"] = df.groupby("R").cumcount() + 1  # posizione FVM nel proprio ruolo (fissa)
    df["_cerca"] = (df["Nome"] + " " + df["Squadra"]).map(lambda x: unidecode(str(x)).lower())
    return df


def aggiorna_blocco(ruolo, i):
    """Callback: copia la selezione del widget nel blocco PRIMA dell'esecuzione dello script,
    così non serve alcun st.rerun() (che interromperebbe filtri e ricerche)."""
    valore = st.session_state.get(f"ms_{ruolo}_{i}")
    if valore is not None:
        st.session_state.blocchi[ruolo][i] = list(valore)


def pulisci_widget_blocchi():
    for k in [k for k in st.session_state if k.startswith("ms_")]:
        del st.session_state[k]


def blocchi_vuoti():
    return {r: [[] for _ in range(N_BLOCCHI)] for r in DIM_BLOCCO}


PORTIERI_PER_SQUADRA = 3  # titolare, secondo, terzo


def blocchi_portieri_per_squadra(df):
    """Blocchi portieri = 2 squadre complete (primo, secondo e terzo portiere di ciascuna).
    Il costo di una squadra e' la somma delle Qt.A dei suoi 3 portieri; le squadre vengono
    ordinate per costo e accoppiate la piu' cara con la piu' economica, la seconda con la
    penultima, ecc., cosi' ogni blocco ha un costo simile."""
    df_p = df[df["R"] == "P"].sort_values(["Qt.A", "FVM"], ascending=False)
    squadre = []
    for sq, g in df_p.groupby("Squadra", sort=False):
        top = g.head(PORTIERI_PER_SQUADRA)
        squadre.append((sq, int(top["Qt.A"].sum()), top["Label"].tolist()))
    squadre.sort(key=lambda t: t[1], reverse=True)
    blocchi_p = []
    while len(squadre) >= 2:
        cara, economica = squadre.pop(0), squadre.pop(-1)
        blocchi_p.append(cara[2] + economica[2])
    if squadre:  # numero dispari di squadre: l'ultima va nel blocco piu' economico
        blocchi_p[-1] += squadre[0][2]
    blocchi_p = blocchi_p[:N_BLOCCHI]
    while len(blocchi_p) < N_BLOCCHI:
        blocchi_p.append([])
    return blocchi_p


def blocchi_serpentina(df):
    """Pre-popola i blocchi a serpentina per FVM decrescente: i primi 10 vanno
    nei blocchi 1..10, i successivi 10 nei blocchi 10..1, e cosi' via.
    I portieri fanno eccezione: 2 squadre complete per blocco (vedi blocchi_portieri_per_squadra)."""
    out = blocchi_vuoti()
    out["P"] = blocchi_portieri_per_squadra(df)
    for ruolo, dim in DIM_BLOCCO.items():
        if ruolo == "P":
            continue
        labels = (df[df["R"] == ruolo]
                  .sort_values("#")["Label"]
                  .head(N_BLOCCHI * dim).tolist())
        for k, label in enumerate(labels):
            giro, pos = divmod(k, N_BLOCCHI)
            blocco = pos if giro % 2 == 0 else N_BLOCCHI - 1 - pos
            out[ruolo][blocco].append(label)
    return out


def percorso(nome):
    slug = re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_")
    return os.path.join(CARTELLA_CAMPIONATI, f"{slug}.json")


def salva(nome, blocchi):
    os.makedirs(CARTELLA_CAMPIONATI, exist_ok=True)
    with open(percorso(nome), "w", encoding="utf-8") as f:
        json.dump({"nome": nome, "blocchi": blocchi, "rinomine": st.session_state.get("rinomine", {})}, f, ensure_ascii=False, indent=2)


def carica(nome):
    with open(percorso(nome), encoding="utf-8") as f:
        return json.load(f)["blocchi"]


def campionati_salvati():
    if not os.path.isdir(CARTELLA_CAMPIONATI):
        return []
    out = []
    for f in sorted(os.listdir(CARTELLA_CAMPIONATI)):
        if f.endswith(".json"):
            with open(os.path.join(CARTELLA_CAMPIONATI, f), encoding="utf-8") as fh:
                out.append(json.load(fh)["nome"])
    return out


FILE_RINOMINE = "rinomine.json"


def carica_rinomine():
    if os.path.exists(FILE_RINOMINE):
        with open(FILE_RINOMINE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def salva_rinomine(rin):
    with open(FILE_RINOMINE, "w", encoding="utf-8") as f:
        json.dump(rin, f, ensure_ascii=False, indent=2)


def applica_rinomine(base, rin):
    """rin: {label originale del CSV: nuovo nome}. Ritorna una copia del listone con i nomi corretti."""
    d = base.copy()
    d["LabelBase"] = d["Label"]
    if rin:
        nuovi = d["LabelBase"].map(rin)
        d["Nome"] = nuovi.fillna(d["Nome"])
        d["Label"] = d["Nome"] + " (" + d["Squadra"] + ")"
        d["_cerca"] = (d["Nome"] + " " + d["Squadra"]).map(lambda x: unidecode(str(x)).lower())
    return d


def rinomina_giocatore(ruolo, i):
    """Callback del data_editor: applica la modifica del nome a listone e blocchi."""
    stato = st.session_state.get(f"ed_{ruolo}_{i}", {})
    righe = st.session_state.get(f"righe_{ruolo}_{i}", [])
    for idx, cambi in stato.get("edited_rows", {}).items():
        if "Nome" not in cambi or int(idx) >= len(righe):
            continue
        label_base, squadra = righe[int(idx)]
        nuovo = str(cambi["Nome"]).strip()
        if not nuovo:
            continue
        rin = st.session_state.rinomine
        vecchio_nome = rin.get(label_base, label_base.rsplit(" (", 1)[0])
        vecchia_label = f"{vecchio_nome} ({squadra})"
        nuova_label = f"{nuovo} ({squadra})"
        if nuova_label == vecchia_label:
            continue
        rin[label_base] = nuovo
        for r in st.session_state.blocchi:
            for b in st.session_state.blocchi[r]:
                for k, p in enumerate(b):
                    if p == vecchia_label:
                        b[k] = nuova_label
        salva_rinomine(rin)
    pulisci_widget_blocchi()


df_base = carica_listone()
if df_base is None:
    st.error(f"Listone non trovato: {LISTONE_CSV}. Esegui prima `python scarica_listone.py`.")
    st.stop()
if "rinomine" not in st.session_state:
    st.session_state.rinomine = carica_rinomine()
df = applica_rinomine(df_base, st.session_state.rinomine)

# ---------------- Sidebar: gestione campionato ----------------
st.sidebar.header("Campionato")
esistenti = campionati_salvati()
scelta = st.sidebar.selectbox("Carica campionato", ["— nuovo —"] + esistenti)
nome_nuovo = st.sidebar.text_input("Nome nuovo campionato", "") if scelta == "— nuovo —" else scelta

if "campionato" not in st.session_state or st.session_state.campionato != nome_nuovo:
    st.session_state.campionato = nome_nuovo
    st.session_state.blocchi = carica(nome_nuovo) if nome_nuovo in esistenti else blocchi_vuoti()
    pulisci_widget_blocchi()

blocchi = st.session_state.blocchi
nome = st.session_state.campionato

if not nome:
    st.info("Inserisci il nome del campionato nella barra laterale per iniziare.")
    st.stop()

st.title(f"🏆 {nome}")
st.caption(LEGENDA)

col_s, col_r = st.sidebar.columns(2)
if col_s.button("💾 Salva", width="stretch"):
    salva(nome, blocchi)
    st.sidebar.success("Salvato")
if col_r.button("🗑️ Svuota", width="stretch"):
    st.session_state.blocchi = blocchi_vuoti()
    pulisci_widget_blocchi()
    st.rerun()
if st.sidebar.button("⚖️ Pre-popola equilibrato (serpentina per FVM)", width="stretch",
                     help="Sostituisce i blocchi attuali. D/C/A: serpentina per FVM (1°-10° nei blocchi 1-10, 11°-20° nei blocchi 10-1, ...). Portieri: 2 squadre complete per blocco (3 portieri ciascuna), accoppiate per bilanciare la Qt.A."):
    st.session_state.blocchi = blocchi_serpentina(df)
    pulisci_widget_blocchi()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("Su Streamlit Cloud i salvataggi non sono permanenti: scarica il file e ricaricalo quando serve.")
st.sidebar.download_button(
    "⬇️ Scarica campionato (JSON)",
    data=json.dumps({"nome": nome, "blocchi": blocchi, "rinomine": st.session_state.rinomine}, ensure_ascii=False, indent=2),
    file_name=f"{re.sub(r'[^a-z0-9]+', '_', nome.lower()).strip('_')}.json",
    mime="application/json", width="stretch",
)
caricato = st.sidebar.file_uploader("⬆️ Carica campionato (JSON)", type="json", key="upload_json")
if caricato is not None and st.session_state.get("upload_fatto") != caricato.file_id:
    try:
        dati = json.load(caricato)
        st.session_state.blocchi = dati["blocchi"]
        if dati.get("rinomine"):
            st.session_state.rinomine.update(dati["rinomine"])
            salva_rinomine(st.session_state.rinomine)
        st.session_state.upload_fatto = caricato.file_id
        pulisci_widget_blocchi()
        st.sidebar.success(f"Caricato: {dati.get('nome', '')}")
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"File non valido: {e}")

rin = st.session_state.rinomine
with st.sidebar.expander(f"✏️ Nomi corretti ({len(rin)})"):
    if not rin:
        st.caption("Nessuna correzione. Fai doppio click su un nome nella tabella di un blocco per modificarlo.")
    for base, nuovo in list(rin.items()):
        c1, c2 = st.columns([4, 1])
        c1.write(f"{base.rsplit(' (', 1)[0]} → **{nuovo}**")
        if c2.button("↩", key=f"undo_rin_{base}", help="Ripristina il nome originale"):
            squadra = base.rsplit(" (", 1)[1][:-1]
            vecchia_label = f"{nuovo} ({squadra})"
            for r in blocchi:
                for b in blocchi[r]:
                    for k, p_ in enumerate(b):
                        if p_ == vecchia_label:
                            b[k] = base
            del rin[base]
            salva_rinomine(rin)
            pulisci_widget_blocchi()
            st.rerun()

# ---------------- Stato: giocatori assegnati ----------------
assegnati = {p for r in blocchi for b in blocchi[r] for p in b}
tot = sum(len(b) for r in blocchi for b in blocchi[r])
tot_max = N_BLOCCHI * sum(DIM_BLOCCO.values())
st.sidebar.metric("Giocatori assegnati", f"{tot} / {tot_max}")
st.sidebar.metric("Rimasti nel listone", len(df) - tot)

# ---------------- Tab per ruolo ----------------
tabs = st.tabs([f"{NOME_RUOLO[r]} ({DIM_BLOCCO[r]}×{N_BLOCCHI})" for r in DIM_BLOCCO] + ["🔁 Scambi", "📋 Listone rimanente", "📚 Listone completo"])

for tab, ruolo in zip(tabs, DIM_BLOCCO):
    with tab:
        dim = DIM_BLOCCO[ruolo]
        df_r = df[df["R"] == ruolo].sort_values("#")
        liberi = df_r[~df_r["Label"].isin(assegnati)]["Label"].tolist()
        st.caption(f"{len(liberi)} {NOME_RUOLO[ruolo].lower()} ancora disponibili nel listone")

        # ---- ricerca: evidenzia il blocco in cui si trova il giocatore ----
        with st.form(key=f"form_blk_{ruolo}", border=False):
            f1, f2, f3 = st.columns([4, 1, 1])
            testo_b = f1.text_input("Trova in quale blocco sta un giocatore", key=f"testo_blk_{ruolo}",
                                    placeholder="es. dimarco — poi premi Cerca o Invio", label_visibility="collapsed")
            invia_b = f2.form_submit_button("🔎 Cerca", width="stretch")
            azzera_b = f3.form_submit_button("✖ Azzera", width="stretch")
        if invia_b:
            st.session_state[f"cerca_blk_{ruolo}"] = testo_b
        if azzera_b:
            st.session_state[f"cerca_blk_{ruolo}"] = ""
        cerca_b = unidecode(st.session_state.get(f"cerca_blk_{ruolo}", "")).lower().strip()
        trovati_per_blocco = {}
        if cerca_b:
            match = set(df_r[df_r["_cerca"].str.contains(cerca_b, regex=False, na=False)]["Label"])
            for i in range(N_BLOCCHI):
                hit = [p for p in blocchi[ruolo][i] if p in match]
                if hit:
                    trovati_per_blocco[i] = hit
            liberi_match = [p for p in liberi if p in match]
            if trovati_per_blocco:
                dove = ", ".join(f"**{ruolo}{i + 1}** ({', '.join(h)})" for i, h in trovati_per_blocco.items())
                st.success(f"🎯 Trovato in: {dove}")
            elif liberi_match:
                st.warning(f"Nessun blocco: {', '.join(liberi_match)} è ancora nel listone rimanente.")
            else:
                st.error(f"Nessun {SINGOLARE[ruolo]} trovato per «{cerca_b}».")

        colonne = st.columns(2)
        for i in range(N_BLOCCHI):
            with colonne[i % 2]:
                attuali = blocchi[ruolo][i]
                pieno = len(attuali) >= dim
                titolo = f"Blocco {ruolo}{i + 1} — {len(attuali)}/{dim}" + (" ✅" if pieno else "")
                evidenzia = i in trovati_per_blocco
                if cerca_b and trovati_per_blocco and not evidenzia:
                    contenitore = st.expander(titolo, expanded=False)   # blocchi non pertinenti: compressi
                else:
                    contenitore = st.container(border=True)
                with contenitore:
                    if evidenzia:
                        st.markdown(f"🎯 **{titolo}** — :green[**{', '.join(trovati_per_blocco[i])}**]")
                    elif not (cerca_b and trovati_per_blocco):
                        st.markdown(f"**{titolo}**")
                    opzioni = attuali + liberi  # i propri giocatori + quelli liberi
                    # lo stato dei blocchi e' l'unica fonte di verita': lo scrivo nel widget PRIMA di crearlo
                    st.session_state[f"ms_{ruolo}_{i}"] = list(attuali)
                    st.multiselect(
                        "Giocatori",
                        options=opzioni,
                        max_selections=dim,
                        key=f"ms_{ruolo}_{i}",
                        label_visibility="collapsed",
                        on_change=aggiorna_blocco,
                        args=(ruolo, i),
                    )
                    if attuali:
                        sub = df_r[df_r["Label"].isin(attuali)][["#", "Nome", "Squadra", "Qt.A", "FVM", "LabelBase"]]
                        st.session_state[f"righe_{ruolo}_{i}"] = list(zip(sub["LabelBase"], sub["Squadra"]))
                        st.data_editor(
                            sub.drop(columns=["LabelBase"]), hide_index=True, width="stretch",
                            column_config={**COLONNE, "Nome": st.column_config.TextColumn(
                                "Nome ✏️", help="Doppio click per correggere il nome. La modifica vale ovunque e viene salvata.")},
                            disabled=["#", "Squadra", "Qt.A", "FVM"],
                            key=f"ed_{ruolo}_{i}", on_change=rinomina_giocatore, args=(ruolo, i),
                        )
                        conteggio = sub["Squadra"].value_counts()
                        # per i portieri 3 per squadra e' voluto: l'avviso scatta solo oltre
                        soglia = PORTIERI_PER_SQUADRA + 1 if ruolo == "P" else SOGLIA_SQUADRA
                        parti = []
                        for sq, n in conteggio.items():
                            if n >= soglia:
                                parti.append(f":red[**{sq} ×{n}**]")
                            elif n == 2 and ruolo != "P":
                                parti.append(f":orange[{sq} ×{n}]")
                            else:
                                parti.append(f"{sq} ×{n}")
                        troppi = [f"{sq} ({n})" for sq, n in conteggio.items() if n >= soglia]
                        avviso = f"  ⚠️ troppi della stessa squadra: {', '.join(troppi)}" if troppi else ""
                        st.caption("Squadre: " + " · ".join(parti) + avviso)

ORDINAMENTI = {
    "FVM ↓": (["FVM", "Qt.A"], [False, False]),
    "Qt.A ↓": (["Qt.A", "FVM"], [False, False]),
    "Qt.I ↓": (["Qt.I", "FVM"], [False, False]),
    "Nome A-Z": (["Nome"], [True]),
    "Ruolo + FVM ↓": (["R", "FVM"], [True, False]),
}
blocco_di = {p: f"{r}{i + 1}" for r in blocchi for i, b in enumerate(blocchi[r]) for p in b}


def tabella_listone(chiave, solo_liberi):
    c1, c2 = st.columns([2, 2])
    filtro_r = c1.multiselect("Ruolo", list(DIM_BLOCCO), default=list(DIM_BLOCCO),
                              format_func=NOME_RUOLO.get, key=f"ruolo_{chiave}")
    ordine = c2.selectbox("Ordina per", list(ORDINAMENTI), key=f"ordine_{chiave}")
    with st.form(key=f"form_{chiave}", border=False):
        f1, f2, f3 = st.columns([4, 1, 1])
        testo = f1.text_input("Cerca nome o squadra", key=f"testo_{chiave}", placeholder="es. malen, int, toure",
                              help="Ignora maiuscole e accenti. Cerca anche nella sigla squadra.", label_visibility="collapsed")
        invia = f2.form_submit_button("🔎 Cerca", width="stretch")
        azzera = f3.form_submit_button("✖ Azzera", width="stretch")
    stato_key = f"cerca_{chiave}"
    if invia:
        st.session_state[stato_key] = testo
    if azzera:
        st.session_state[stato_key] = ""
    cerca = st.session_state.get(stato_key, "")
    v = df.copy()
    v["Blocco"] = v["Label"].map(blocco_di).fillna("")
    if solo_liberi:
        v = v[v["Blocco"] == ""]
    v = v[v["R"].isin(filtro_r)]
    if cerca:
        v = v[v["_cerca"].str.contains(unidecode(cerca).lower().strip(), regex=False, na=False)]
    cols, asc = ORDINAMENTI[ordine]
    v = v.sort_values(cols, ascending=asc)
    if cerca:
        st.write(f"{len(v)} giocatori — 🔎 filtro attivo: **{cerca}**")
    else:
        st.write(f"{len(v)} giocatori — nessun filtro nome (scrivi nel campo e premi **Cerca** o Invio)")
    st.dataframe(v[["#", "Nome", "Squadra", "R", "Qt.I", "Qt.A", "FVM", "Blocco"]],
                 hide_index=True, width="stretch", height=600, column_config=COLONNE)


def etichetta(label):
    riga = df[df["Label"] == label].iloc[0]
    b = blocco_di.get(label, "listone")
    return f"#{riga['#']} {label} — FVM {int(riga['FVM'])} — {b}"


def fvm_blocco(ruolo, i):
    return int(df[df["Label"].isin(blocchi[ruolo][i])]["FVM"].sum())


def trova_blocco(label):
    """Ritorna l'indice del blocco (0-based) in cui si trova il giocatore, nel suo ruolo."""
    r = df.loc[df["Label"] == label, "R"].iloc[0]
    for i, b in enumerate(blocchi[r]):
        if label in b:
            return r, i
    return r, None


with tabs[-3]:
    st.caption("Modifica i blocchi dopo averli creati: scambia due giocatori di blocchi diversi "
               "oppure sostituisci un giocatore con uno del listone rimanente. Ricordati di **Salvare** dopo.")
    ruolo_sc = st.radio("Ruolo", list(DIM_BLOCCO), format_func=NOME_RUOLO.get, horizontal=True, key="ruolo_scambi")
    df_sc = df[df["R"] == ruolo_sc].sort_values("#")
    assegnati_r = [l for l in df_sc["Label"] if l in blocco_di]
    liberi_r = [l for l in df_sc["Label"] if l not in blocco_di]

    c_sx, c_dx = st.columns(2)
    with c_sx, st.container(border=True):
        st.markdown("**🔁 Scambia due giocatori di blocchi diversi**")
        a = st.selectbox("Giocatore A", assegnati_r, index=None, format_func=etichetta, key="sc_a",
                         placeholder="scrivi per cercare…")
        b_opts = [l for l in assegnati_r if a is None or blocco_di.get(l) != blocco_di.get(a)]
        b = st.selectbox("Giocatore B (di un altro blocco)", b_opts, index=None, format_func=etichetta, key="sc_b",
                         placeholder="scrivi per cercare…")
        if a and b:
            _, ia = trova_blocco(a)
            _, ib = trova_blocco(b)
            fa, fb = fvm_blocco(ruolo_sc, ia), fvm_blocco(ruolo_sc, ib)
            da = int(df.loc[df["Label"] == b, "FVM"].iloc[0]) - int(df.loc[df["Label"] == a, "FVM"].iloc[0])
            st.info(f"{ruolo_sc}{ia + 1}: FVM {fa} → {fa + da}  ·  {ruolo_sc}{ib + 1}: FVM {fb} → {fb - da}")
            if st.button("Scambia", type="primary", key="btn_scambia"):
                blocchi[ruolo_sc][ia][blocchi[ruolo_sc][ia].index(a)] = b
                blocchi[ruolo_sc][ib][blocchi[ruolo_sc][ib].index(b)] = a
                st.session_state.setdefault("storico", []).append(("scambio", ruolo_sc, ia, a, ib, b))
                pulisci_widget_blocchi()
                st.rerun()

    with c_dx, st.container(border=True):
        st.markdown("**🔄 Sostituisci con un giocatore del listone rimanente**")
        esce = st.selectbox("Esce (dal blocco)", assegnati_r, index=None, format_func=etichetta, key="sc_esce",
                            placeholder="scrivi per cercare…")
        entra = st.selectbox("Entra (dal listone rimanente)", liberi_r, index=None, format_func=etichetta, key="sc_entra",
                             placeholder="scrivi per cercare…")
        if esce and entra:
            _, ie = trova_blocco(esce)
            fe = fvm_blocco(ruolo_sc, ie)
            d = int(df.loc[df["Label"] == entra, "FVM"].iloc[0]) - int(df.loc[df["Label"] == esce, "FVM"].iloc[0])
            st.info(f"{ruolo_sc}{ie + 1}: FVM {fe} → {fe + d}")
            if st.button("Sostituisci", type="primary", key="btn_sost"):
                blocchi[ruolo_sc][ie][blocchi[ruolo_sc][ie].index(esce)] = entra
                st.session_state.setdefault("storico", []).append(("sostituzione", ruolo_sc, ie, esce, None, entra))
                pulisci_widget_blocchi()
                st.rerun()

    storico = st.session_state.get("storico", [])
    if storico:
        st.markdown("**Storico operazioni (questa sessione)**")
        for tipo, r, i1, x, i2, y in reversed(storico[-10:]):
            if tipo == "scambio":
                st.write(f"🔁 {x} ({r}{i1 + 1}) ⇄ {y} ({r}{i2 + 1})")
            else:
                st.write(f"🔄 {r}{i1 + 1}: esce {x}, entra {y}")
        if st.button("↩️ Annulla ultima operazione", key="btn_undo"):
            tipo, r, i1, x, i2, y = storico.pop()
            if tipo == "scambio":
                blocchi[r][i1][blocchi[r][i1].index(y)] = x
                blocchi[r][i2][blocchi[r][i2].index(x)] = y
            else:
                blocchi[r][i1][blocchi[r][i1].index(y)] = x
            pulisci_widget_blocchi()
            st.rerun()

with tabs[-2]:
    st.caption("Solo i giocatori NON ancora assegnati a un blocco.")
    tabella_listone("rimanente", solo_liberi=True)

with tabs[-1]:
    st.caption("Tutto il listone originale (553 giocatori). La colonna Blocco indica dove è stato assegnato ciascun giocatore.")
    tabella_listone("completo", solo_liberi=False)
