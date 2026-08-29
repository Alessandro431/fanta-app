"""Frontend Streamlit per creare un campionato Fantacalcio a blocchi.
Per ogni ruolo ci sono 10 blocchi con un numero fisso di giocatori:
P=6, D=8, C=10, A=6. Un giocatore assegnato a un blocco sparisce dal listone.
Avvio:  streamlit run blocchi.py
"""
import json
import os
import re
from datetime import datetime

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
    if "Fuori" not in df.columns:
        df["Fuori"] = 0
    df["Fuori"] = df["Fuori"].fillna(0).astype(int)
    df = df.sort_values(["FVM", "Qt.A"], ascending=False).reset_index(drop=True)
    # posizione FVM nel proprio ruolo (fissa), calcolata solo sui giocatori ancora in Serie A
    attivi = df[df["Fuori"] == 0]
    df["#"] = attivi.groupby("R").cumcount() + 1
    df["#"] = df["#"].astype("Int64")
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
# Coppie di squadre FISSE per i blocchi portieri (P1..P10). Se una squadra non e' in listone,
# il blocco resta parziale; le squadre non elencate vengono accoppiate automaticamente in coda.
COPPIE_PORTIERI = [
    ("JUV", "TOR"), ("ROM", "MON"), ("INT", "FRO"), ("COM", "VEN"), ("ATA", "SAS"),
    ("MIL", "GEN"), ("NAP", "UDI"), ("LEC", "PAR"), ("FIO", "CAG"), ("BOL", "LAZ"),
]


def blocchi_portieri_per_squadra(df):
    """Blocchi portieri = 2 squadre complete (primo, secondo e terzo portiere di ciascuna),
    secondo le coppie fisse COPPIE_PORTIERI. Eventuali squadre non elencate vengono accoppiate
    per costo (somma Qt.A dei 3 portieri): la piu' cara con la piu' economica."""
    df_p = df[df["R"] == "P"].sort_values(["Qt.A", "FVM"], ascending=False)
    squadre = []
    for sq, g in df_p.groupby("Squadra", sort=False):
        top = g.head(PORTIERI_PER_SQUADRA)
        squadre.append((sq, int(top["Qt.A"].sum()), top["Label"].tolist()))
    squadre.sort(key=lambda t: t[1], reverse=True)
    blocchi_p = []
    per_sigla = {sq: labels for sq, _, labels in squadre}
    for a, b in COPPIE_PORTIERI:  # prima le coppie fisse
        blocchi_p.append(per_sigla.pop(a, []) + per_sigla.pop(b, []))
    squadre = [t for t in squadre if t[0] in per_sigla]  # eventuali squadre rimaste
    while len(squadre) >= 2 and len(blocchi_p) < N_BLOCCHI:
        cara, economica = squadre.pop(0), squadre.pop(-1)
        blocchi_p.append(cara[2] + economica[2])
    if squadre and blocchi_p:  # squadre avanzate: nell'ultimo blocco
        for t in squadre:
            blocchi_p[-1] += t[2]
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


def listone_corrente_rif(base):
    """Istantanea del listone (per Id) da salvare nel campionato come riferimento per In/Out."""
    return {str(r.Id): {"Nome": r.Nome, "Squadra": r.Squadra, "R": r.R, "Fuori": int(r.Fuori)}
            for r in base.itertuples()}


def dati_campionato(nome, blocchi):
    """Tutto cio' che va salvato/esportato: blocchi, nomi corretti, storico scambi e listone di riferimento."""
    return {
        "nome": nome,
        "blocchi": blocchi,
        "rinomine": st.session_state.get("rinomine", {}),
        "scambi": st.session_state.get("storico", []),
        "listone_rif": st.session_state.get("listone_rif", {}),
    }


def salva(nome, blocchi):
    os.makedirs(CARTELLA_CAMPIONATI, exist_ok=True)
    with open(percorso(nome), "w", encoding="utf-8") as f:
        json.dump(dati_campionato(nome, blocchi), f, ensure_ascii=False, indent=2)


def carica(nome):
    with open(percorso(nome), encoding="utf-8") as f:
        dati = json.load(f)
    st.session_state.storico = [tuple(x) for x in dati.get("scambi", [])]
    st.session_state.listone_rif = dati.get("listone_rif") or listone_corrente_rif(df_base)
    return dati["blocchi"]


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

# ---------------- Sidebar: due tab (Scambi | Campionato) ----------------
st.markdown("<style>[data-testid='stSidebar']{min-width:430px;max-width:430px}</style>", unsafe_allow_html=True)
main = st.container()
tab_sc, tab_camp = st.sidebar.tabs(["🔁 Scambi", "🏆 Campionato"])
with tab_camp:
    # ---------------- Sidebar: gestione campionato ----------------
    st.header("Campionato")
    esistenti = campionati_salvati()
    scelta = st.selectbox("Carica campionato", ["— nuovo —"] + esistenti)
    nome_nuovo = st.text_input("Nome nuovo campionato", "") if scelta == "— nuovo —" else scelta

    if "campionato" not in st.session_state or st.session_state.campionato != nome_nuovo:
        st.session_state.campionato = nome_nuovo
        if nome_nuovo in esistenti:
            st.session_state.blocchi = carica(nome_nuovo)
        else:
            st.session_state.blocchi = blocchi_vuoti()
            st.session_state.storico = []
            st.session_state.listone_rif = listone_corrente_rif(df_base)
        pulisci_widget_blocchi()

    blocchi = st.session_state.blocchi
    nome = st.session_state.campionato

    if not nome:
        main.info("Inserisci il nome del campionato nella barra laterale (tab 🏆 Campionato) per iniziare.")
        st.stop()

    main.title(f"🏆 {nome}")
    main.caption(LEGENDA)

    n_fuori = int(df["Fuori"].sum())
    mostra_fuori = st.toggle(
        f"Mostra anche i {n_fuori} giocatori fuori dalla Serie A ⚠️", value=False,
        help="Sul sito Fantacalcio.it sono marcati con * (\"Non gioca più in Serie A\"): ceduti all'estero o svincolati. "
             "Di default sono esclusi da listoni, pre-popolamento e menu.")
    df_pool = df if mostra_fuori else df[df["Fuori"] == 0]
    FUORI_SET = set(df[df["Fuori"] == 1]["Label"])

    col_s, col_r = st.columns(2)
    if col_s.button("💾 Salva", width="stretch"):
        salva(nome, blocchi)
        st.success("Salvato")
    if col_r.button("🗑️ Svuota", width="stretch"):
        st.session_state.blocchi = blocchi_vuoti()
        pulisci_widget_blocchi()
        st.rerun()
    if st.button("⚖️ Pre-popola equilibrato (serpentina per FVM)", width="stretch",
                         help="Sostituisce i blocchi attuali. D/C/A: serpentina per FVM (1°-10° nei blocchi 1-10, 11°-20° nei blocchi 10-1, ...). Portieri: 2 squadre complete per blocco (3 portieri ciascuna) secondo le coppie fisse JUV+TOR, ROM+MON, INT+FRO, COM+VEN, ATA+SAS, MIL+GEN, NAP+UDI, LEC+PAR, FIO+CAG, BOL+LAZ."):
        st.session_state.blocchi = blocchi_serpentina(df_pool)
        pulisci_widget_blocchi()
        st.rerun()

    st.divider()
    st.caption("Su Streamlit Cloud i salvataggi non sono permanenti: scarica il file e ricaricalo quando serve.")
    st.download_button(
        "⬇️ Scarica campionato (JSON)",
        data=json.dumps(dati_campionato(nome, blocchi), ensure_ascii=False, indent=2),
        file_name=f"{re.sub(r'[^a-z0-9]+', '_', nome.lower()).strip('_')}.json",
        mime="application/json", width="stretch",
    )
    caricato = st.file_uploader("⬆️ Carica campionato (JSON)", type="json", key="upload_json")
    importa_portieri = st.checkbox("Importa anche i portieri", value=True,
                                           help="Acceso (default): importa tutti i ruoli. Spento: solo Difensori, Centrocampisti e Attaccanti; "
                                                "i blocchi Portieri attuali restano com'erano.")
    if caricato is not None and st.session_state.get("upload_fatto") != caricato.file_id:
        try:
            dati = json.load(caricato)
            nuovi_blocchi = blocchi_vuoti()
            nuovi_blocchi.update({r: v for r, v in dati["blocchi"].items() if r in DIM_BLOCCO})
            if not importa_portieri:
                nuovi_blocchi["P"] = st.session_state.blocchi["P"]  # ignora i portieri del file
            st.session_state.blocchi = nuovi_blocchi
            st.session_state.storico = [tuple(x) for x in dati.get("scambi", [])]
            if dati.get("listone_rif"):
                st.session_state.listone_rif = dati["listone_rif"]
            if dati.get("rinomine"):
                st.session_state.rinomine.update(dati["rinomine"])
                salva_rinomine(st.session_state.rinomine)
            st.session_state.upload_fatto = caricato.file_id
            pulisci_widget_blocchi()
            st.session_state.msg_upload = f"Caricato: {dati.get('nome', '')}" + ("" if importa_portieri else " (portieri ignorati)")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"File non valido: {e}")
    if st.session_state.get("msg_upload"):
        st.success(st.session_state.pop("msg_upload"))

    rin = st.session_state.rinomine
    with st.expander(f"✏️ Nomi corretti ({len(rin)})"):
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
    st.metric("Giocatori assegnati", f"{tot} / {tot_max}")
    st.metric("Rimasti nel listone", len(df) - tot)

# ---------------- Confronto listone di riferimento vs attuale (In / Out) ----------------
rif = st.session_state.get("listone_rif") or {}
cur = {str(r.Id): {"Nome": r.Nome, "Squadra": r.Squadra, "R": r.R, "Fuori": int(r.Fuori)} for r in df_base.itertuples()}
nome_rin = st.session_state.rinomine


def label_di(info):
    base = f"{info['Nome']} ({info['Squadra']})"
    return f"{nome_rin[base]} ({info['Squadra']})" if base in nome_rin else base


_by_id = df_base.assign(_id=df_base["Id"].astype(str)).set_index("_id")
in_blocchi = {p: f"{r}{i + 1}" for r in blocchi for i, b in enumerate(blocchi[r]) for p in b}
usciti, nuovi, trasferiti = [], [], []
for pid, old_ in rif.items():
    now = cur.get(pid)
    lab_old = label_di(old_)
    if now is None or (old_["Fuori"] == 0 and now["Fuori"] == 1):
        if old_["Fuori"] == 0:
            usciti.append({"Giocatore": lab_old, "R": old_["R"], "Blocco": in_blocchi.get(lab_old, "—"),
                           "Motivo": "rimosso dal listone" if now is None else "non gioca più in Serie A (*)"})
    elif now["Squadra"] != old_["Squadra"]:
        trasferiti.append((pid, lab_old, label_di(now), old_["Squadra"], now["Squadra"], now["R"]))
for pid, now in cur.items():
    old_ = rif.get(pid)
    if now["Fuori"] == 0 and (old_ is None or old_["Fuori"] == 1):
        riga = _by_id.loc[pid]
        nuovi.append({"Giocatore": label_di(now), "R": now["R"], "Squadra": now["Squadra"],
                      "Qt.A": int(riga["Qt.A"]), "FVM": int(riga["FVM"]),
                      "Motivo": "nuovo in listone" if old_ is None else "rientrato in Serie A"})

# trasferimenti dentro la Serie A: la label cambia squadra -> aggiorno i blocchi automaticamente
for pid, lab_old, lab_new, sq_old, sq_new, r_ in trasferiti:
    for r in blocchi:
        for b in blocchi[r]:
            for k, p_ in enumerate(b):
                if p_ == lab_old:
                    b[k] = lab_new
in_blocchi = {p: f"{r}{i + 1}" for r in blocchi for i, b in enumerate(blocchi[r]) for p in b}
n_out_blocchi = sum(1 for u in usciti if u["Blocco"] != "—")
badge_inout = f"📤 Out {len(usciti)} / 📥 In {len(nuovi)}" + (" ⚠️" if n_out_blocchi else "")

# ---------------- Tab per ruolo ----------------
tabs = st.tabs([f"{NOME_RUOLO[r]} ({DIM_BLOCCO[r]}×{N_BLOCCHI})" for r in DIM_BLOCCO] + ["📋 Listone rimanente", "📚 Listone completo", badge_inout])

for tab, ruolo in zip(tabs, DIM_BLOCCO):
    with tab:
        dim = DIM_BLOCCO[ruolo]
        df_r = df[df["R"] == ruolo].sort_values("#")
        liberi = df_r[~df_r["Label"].isin(assegnati) & df_r["Label"].isin(df_pool["Label"])]["Label"].tolist()
        fuori_nei_blocchi = [p for b in blocchi[ruolo] for p in b if p in FUORI_SET]
        if fuori_nei_blocchi:
            st.warning("⚠️ Nei blocchi ci sono giocatori che non giocano più in Serie A: "
                       + ", ".join(fuori_nei_blocchi) + ". Sostituiscili dalla tab Scambi o rifai il pre-popolamento.")
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
                        sub = df_r[df_r["Label"].isin(attuali)][["#", "Nome", "Squadra", "Qt.A", "FVM", "LabelBase", "Fuori"]].copy()
                        sub["Squadra"] = sub["Squadra"].where(sub["Fuori"] == 0, sub["Squadra"] + " ⚠️")
                        sub = sub.drop(columns=["Fuori"])
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
    v = df_pool.copy()
    v["Blocco"] = v["Label"].map(blocco_di).fillna("")
    v["Nome"] = v["Nome"].where(v["Fuori"] == 0, "⚠️ " + v["Nome"])
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


with tab_sc:
    st.caption("Scambia due giocatori di blocchi diversi o sostituisci con uno del listone rimanente. "
               "I blocchi a destra si aggiornano subito; ricordati di **Salvare**.")
    ruolo_sc = st.radio("Ruolo", list(DIM_BLOCCO), format_func=NOME_RUOLO.get, horizontal=True, key="ruolo_scambi")
    df_sc = df[df["R"] == ruolo_sc].sort_values("#")
    assegnati_r = [l for l in df_sc["Label"] if l in blocco_di]
    pool_labels = set(df_pool["Label"])
    liberi_r = [l for l in df_sc["Label"] if l not in blocco_di and l in pool_labels]

    with st.container(border=True):
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
                st.session_state.setdefault("storico", []).append(("scambio", ruolo_sc, ia, a, ib, b, datetime.now().strftime("%d/%m %H:%M")))
                pulisci_widget_blocchi()
                st.rerun()

    with st.container(border=True):
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
                st.session_state.setdefault("storico", []).append(("sostituzione", ruolo_sc, ie, esce, None, entra, datetime.now().strftime("%d/%m %H:%M")))
                pulisci_widget_blocchi()
                st.rerun()

    storico = st.session_state.get("storico", [])
    if storico:
        st.markdown(f"**Storico operazioni ({len(storico)})** — viene salvato con il campionato")
        for voce in reversed(storico[-15:]):
            tipo, r, i1, x, i2, y = voce[:6]
            quando = f"`{voce[6]}` " if len(voce) > 6 else ""
            if tipo == "scambio":
                st.write(f"{quando}🔁 {x} ({r}{i1 + 1}) ⇄ {y} ({r}{i2 + 1})")
            else:
                st.write(f"{quando}🔄 {r}{i1 + 1}: esce {x}, entra {y}")
        if st.button("↩️ Annulla ultima operazione", key="btn_undo"):
            tipo, r, i1, x, i2, y = storico.pop()[:6]
            if tipo == "scambio":
                blocchi[r][i1][blocchi[r][i1].index(y)] = x
                blocchi[r][i2][blocchi[r][i2].index(x)] = y
            else:
                blocchi[r][i1][blocchi[r][i1].index(y)] = x
            pulisci_widget_blocchi()
            st.rerun()

with tabs[-3]:
    st.caption("Solo i giocatori NON ancora assegnati a un blocco.")
    tabella_listone("rimanente", solo_liberi=True)

with tabs[-2]:
    st.caption(f"Tutto il listone ({len(df_pool)} giocatori). La colonna Blocco indica dove è stato assegnato ciascun giocatore.")
    tabella_listone("completo", solo_liberi=False)

with tabs[-1]:
    st.caption("Confronto tra il listone di riferimento del campionato (istantanea presa quando l'hai creato o "
               "aggiornato l'ultima volta) e il listone scaricato adesso. Cosi', quando riscarichi i dati, vedi "
               "chi e' andato via dai tuoi blocchi e chi e' arrivato di nuovo.")
    if not rif:
        st.info("Nessun listone di riferimento: viene creato al primo salvataggio.")
    c_out, c_in = st.columns(2)
    with c_out:
        st.subheader(f"📤 Out ({len(usciti)})")
        if usciti:
            st.dataframe(pd.DataFrame(usciti).sort_values(["Blocco", "R"]), hide_index=True, width="stretch")
            if n_out_blocchi and st.button(f"🗑️ Togli dai blocchi i {n_out_blocchi} usciti", type="primary"):
                labels_out = {u["Giocatore"] for u in usciti if u["Blocco"] != "—"}
                for r in blocchi:
                    for b in blocchi[r]:
                        b[:] = [p_ for p_ in b if p_ not in labels_out]
                pulisci_widget_blocchi()
                st.rerun()
        else:
            st.success("Nessun giocatore uscito.")
    with c_in:
        st.subheader(f"📥 In ({len(nuovi)})")
        if nuovi:
            st.dataframe(pd.DataFrame(nuovi).sort_values(["R", "FVM"], ascending=[True, False]),
                         hide_index=True, width="stretch", column_config=COLONNE)
            st.caption("Per inserirli usa la tab Scambi (Sostituisci) o il menu del blocco.")
        else:
            st.success("Nessun giocatore nuovo.")
    if trasferiti:
        st.subheader(f"🔀 Cambiato squadra in Serie A ({len(trasferiti)})")
        st.dataframe(pd.DataFrame([{"Giocatore": n, "Da": a, "A": b, "R": r} for _, o, n, a, b, r in trasferiti]),
                     hide_index=True, width="stretch")
        st.caption("Le etichette nei blocchi sono state aggiornate automaticamente con la nuova squadra.")
    st.divider()
    if st.button("✅ Ho gestito tutto: aggiorna il listone di riferimento a quello attuale"):
        st.session_state.listone_rif = listone_corrente_rif(df_base)
        st.rerun()
    st.caption("Il riferimento viene salvato con il campionato (Salva / Scarica JSON).")
