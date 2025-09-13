import streamlit as st
import pandas as pd
from datetime import date, time, timedelta
from typing import List, Optional, Tuple
import io
import os

st.set_page_config(page_title="Ryanair Finder", page_icon="✈️", layout="wide")
st.title("✈️ Ryanair Finder (Web)")
st.caption("ryanair-py • oneway / return / duration • multi origini/destinazioni • diretti • giorni/orari • prezzo • ordinamento • export CSV/XLSX")

# ---- Libreria backend
try:
    from ryanair import Ryanair
except Exception:
    st.error("Impossibile importare 'ryanair'. Aggiungi il pacchetto 'ryanair-py' in requirements.txt.")
    st.stop()

# ---- Utilità
IT_DOW = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

def fmt_it(dt):
    if not dt:
        return ""
    try:
        w = IT_DOW[dt.weekday()]
        return f"{w} {dt.day:02d}/{dt.month:02d}/{dt.year} {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return str(dt)

def parse_csv(text: str) -> List[str]:
    return [x.strip().upper() for x in (text or "").split(",") if x.strip()]

def is_nonstop_leg(obj) -> Optional[bool]:
    if hasattr(obj, "stops"):
        try:
            return int(getattr(obj, "stops")) == 0
        except Exception:
            pass
    if hasattr(obj, "isDirect"):
        val = getattr(obj, "isDirect")
        if isinstance(val, bool):
            return val
    segs = getattr(obj, "segments", None)
    if isinstance(segs, (list, tuple)):
        return len(segs) <= 1
    return None

def keep_by_weekday(dt, weekdays_it: List[str]) -> bool:
    if not weekdays_it or not dt:
        return True
    it = IT_DOW[dt.weekday()]
    return it in weekdays_it

def keep_by_time_window(dt, after: Optional[time], before: Optional[time]) -> bool:
    if not dt:
        return True
    t = dt.time()
    if after and t < after:
        return False
    if before and t > before:
        return False
    return True

def build_api(currency: str, adults: int, children: int):
    # fallback per versioni di ryanair-py senza adults/children
    try:
        return Ryanair(currency=currency, adults=adults, children=children)
    except TypeError:
        return Ryanair(currency=currency)

# ---- Aeroporti (picker)
# 1) tenta di caricare airports.csv locale (IATA,City,Airport,Country)
AIRPORTS: List[Tuple[str,str,str,str]] = []
csv_path = "airports.csv"
if os.path.exists(csv_path):
    try:
        df_air = pd.read_csv(csv_path)
        # expected columns: IATA,City,Airport,Country
        for _, r in df_air.iterrows():
            AIRPORTS.append((str(r["IATA"]).upper(), str(r["City"]), str(r["Airport"]), str(r.get("Country",""))))
    except Exception as e:
        st.warning(f"Impossibile leggere airports.csv ({e}). Uso lista interna di esempi.")

if not AIRPORTS:
    # 2) lista interna minima (espandila a piacere o usa airports.csv)
    AIRPORTS = [
        ("BGY","Bergamo","Orio al Serio","IT"),
        ("MXP","Milano","Malpensa","IT"),
        ("LIN","Milano","Linate","IT"),
        ("FCO","Roma","Fiumicino","IT"),
        ("CIA","Roma","Ciampino","IT"),
        ("TSF","Treviso","Treviso","IT"),
        ("VCE","Venezia","Marco Polo","IT"),
        ("NAP","Napoli","Capodichino","IT"),
        ("PMO","Palermo","Falcone–Borsellino","IT"),
        ("CAG","Cagliari","Elmas","IT"),
        ("CAG","Cagliari","Elmas","IT"),
        ("BCN","Barcellona","El Prat","ES"),
        ("MAD","Madrid","Barajas","ES"),
        ("PMI","Palma di Maiorca","PMI","ES"),
        ("STN","Londra","Stansted","UK"),
        ("LTN","Londra","Luton","UK"),
        ("DUB","Dublino","Dublin","IE"),
        ("CDG","Parigi","Charles de Gaulle","FR"),
        ("ORY","Parigi","Orly","FR"),
        ("AMS","Amsterdam","Schiphol","NL"),
        ("BRU","Bruxelles","Brussels","BE"),
        ("BUD","Budapest","Budapest","HU"),
        ("PRG","Praga","Václav Havel","CZ"),
        ("VIE","Vienna","Schwechat","AT"),
        ("ATH","Atene","Eleftherios Venizelos","GR"),
        ("LIS","Lisbona","Humberto Delgado","PT"),
        ("OPO","Porto","Francisco Sá Carneiro","PT"),
    ]

def airport_label(iata, city, name, country):
    suffix = f" · {country}" if country else ""
    return f"{city} — {name} ({iata}){suffix}"

def pick_airports_multiselect(key: str, default_codes: List[str]) -> List[str]:
    # costruiamo mapping label->IATA per ricerca testuale
    options = [airport_label(*a) for a in AIRPORTS]
    code_map = {airport_label(*a): a[0] for a in AIRPORTS}
    # pre-selezione in base ai codici (se presenti in lista)
    defaults = [lbl for lbl in options if code_map[lbl] in set(default_codes)]
    picked_labels = st.multiselect("Seleziona aeroporti", options, default=defaults, key=key)
    return [code_map[lbl] for lbl in picked_labels]

def pick_airport_single(key: str, default_code: Optional[str]) -> Optional[str]:
    options = ["(Nessuna)"] + [airport_label(*a) for a in AIRPORTS]
    code_map = {airport_label(*a): a[0] for a in AIRPORTS}
    default_label = "(Nessuna)"
    if default_code:
        for a in AIRPORTS:
            if a[0].upper() == default_code.upper():
                default_label = airport_label(*a)
                break
    lbl = st.selectbox("Seleziona destinazione (singola, opzionale)", options, index=options.index(default_label), key=key)
    return None if lbl == "(Nessuna)" else code_map[lbl]

# ---- Ricerca
@st.cache_data(show_spinner=True)
def search_oneway(origins: List[str], dest_single: Optional[str], dests_multi: List[str],
                  start: date, end: date, currency: str, adults: int, children: int,
                  nonstop: bool, price_max: Optional[float],
                  weekday: List[str], dep_after: Optional[time], dep_before: Optional[time],
                  arr_after: Optional[time], arr_before: Optional[time]) -> pd.DataFrame:
    api = build_api(currency, adults, children)
    rows = []
    for origin in origins:
        flights = api.get_cheapest_flights(origin, start, end)
        # filtro destinazioni (singola o multiple)
        def match_dest(code):
            if dest_single:
                return code.upper() == dest_single.upper()
            return (not dests_multi) or (code.upper() in dests_multi)
        flights = [f for f in flights if match_dest(getattr(f, "destination", ""))]

        # diretti
        if nonstop:
            tmp = []
            for f in flights:
                ns = is_nonstop_leg(f)
                if ns is True or ns is None:
                    tmp.append(f)
            flights = tmp

        # prezzo / pax
        if price_max is not None:
            flights = [f for f in flights if isinstance(getattr(f, "price", None), (int,float)) and f.price <= price_max]

        # giorni/orari
        flights = [f for f in flights if keep_by_weekday(getattr(f, "departureTime", None), weekday)]
        flights = [f for f in flights if keep_by_time_window(getattr(f, "departureTime", None), dep_after, dep_before)]
        flights = [f for f in flights if keep_by_time_window(getattr(f, "arrivalTime", None), arr_after, arr_before)]

        for f in flights:
            rows.append({
                "PREZZO/PAX": getattr(f, "price", None),
                "VALUTA": getattr(f, "currency", currency),
                "ORIGINE": getattr(f, "origin",""),
                "DEST": getattr(f,"destination",""),
                "PARTENZA": getattr(f, "departureTime", None),
                "ARRIVO": getattr(f, "arrivalTime", None),
                "VOLO": getattr(f,"flightNumber",""),
                "PARTENZA (IT)": fmt_it(getattr(f, "departureTime", None)),
                "ARRIVO (IT)": fmt_it(getattr(f, "arrivalTime", None)),
            })
    return pd.DataFrame(rows)

@st.cache_data(show_spinner=True)
def search_return(origins: List[str], dest_single: Optional[str], dests_multi: List[str],
                  ob_start: date, ob_end: date, ib_start: date, ib_end: date,
                  currency: str, adults: int, children: int,
                  nonstop: bool, price_max: Optional[float],
                  weekday: List[str], dep_after: Optional[time], dep_before: Optional[time],
                  arr_after: Optional[time], arr_before: Optional[time]) -> pd.DataFrame:
    api = build_api(currency, adults, children)
    rows = []
    for origin in origins:
        trips = api.get_cheapest_return_flights(origin, ob_start, ob_end, ib_start, ib_end)

        def match_dest(code):
            if dest_single:
                return code.upper() == dest_single.upper()
            return (not dests_multi) or (code.upper() in dests_multi)
        trips = [t for t in trips if match_dest(getattr(t.outbound, "destination", ""))]

        if nonstop:
            tmp = []
            for t in trips:
                ns_out = is_nonstop_leg(t.outbound)
                ns_in = is_nonstop_leg(t.inbound)
                ok_out = (ns_out is True) or (ns_out is None)
                ok_in = (ns_in is True) or (ns_in is None)
                if ok_out and ok_in:
                    tmp.append(t)
            trips = tmp

        if price_max is not None:
            trips = [t for t in trips if isinstance(getattr(t, "totalPrice", None), (int,float)) and t.totalPrice <= price_max]

        trips = [t for t in trips if keep_by_weekday(getattr(t.outbound, "departureTime", None), weekday)]
        trips = [t for t in trips if keep_by_time_window(getattr(t.outbound, "departureTime", None), dep_after, dep_before)]
        trips = [t for t in trips if keep_by_time_window(getattr(t.outbound, "arrivalTime", None), arr_after, arr_before)]

        for t in trips:
            out, inn = t.outbound, t.inbound
            rows.append({
                "PREZZO/PAX (TOT A/R)": getattr(t, "totalPrice", None),
                "VALUTA": getattr(out, "currency", currency),
                "OUT: PREZZO/PAX": getattr(out, "price", None),
                "OUT: PARTENZA": getattr(out, "departureTime", None),
                "OUT: ARRIVO": getattr(out, "arrivalTime", None),
                "OUT: VOLO": getattr(out, "flightNumber", ""),
                "IN: PREZZO/PAX": getattr(inn, "price", None),
                "IN: PARTENZA": getattr(inn, "departureTime", None),
                "IN: ARRIVO": getattr(inn, "arrivalTime", None),
                "IN: VOLO": getattr(inn, "flightNumber", ""),
                "ORIGINE": getattr(out, "origin", ""),
                "DEST": getattr(out, "destination", ""),
                "OUT: PARTENZA (IT)": fmt_it(getattr(out, "departureTime", None)),
                "OUT: ARRIVO (IT)": fmt_it(getattr(out, "arrivalTime", None)),
                "IN: PARTENZA (IT)": fmt_it(getattr(inn, "departureTime", None)),
                "IN: ARRIVO (IT)": fmt_it(getattr(inn, "arrivalTime", None)),
            })
    return pd.DataFrame(rows)

@st.cache_data(show_spinner=True)
def search_duration(origins: List[str], dest_single: Optional[str], dests_multi: List[str],
                    start: date, end: date, days_values: List[int], step_days: int,
                    currency: str, adults: int, children: int,
                    nonstop: bool, price_max: Optional[float],
                    weekday: List[str], dep_after: Optional[time], dep_before: Optional[time],
                    arr_after: Optional[time], arr_before: Optional[time]) -> pd.DataFrame:
    api = build_api(currency, adults, children)
    rows = []
    for origin in origins:
        for dv in days_values:
            stay = timedelta(days=dv)
            last_departure = end - stay
            current = start
            while current <= last_departure:
                out_start = out_end = current
                in_start = in_end = current + stay
                trips = api.get_cheapest_return_flights(origin, out_start, out_end, in_start, in_end)

                def match_dest(code):
                    if dest_single:
                        return code.upper() == dest_single.upper()
                    return (not dests_multi) or (code.upper() in dests_multi)
                trips = [t for t in trips if match_dest(getattr(t.outbound, "destination", ""))]

                if nonstop:
                    tmp = []
                    for t in trips:
                        ns_out = is_nonstop_leg(t.outbound)
                        ns_in = is_nonstop_leg(t.inbound)
                        ok_out = (ns_out is True) or (ns_out is None)
                        ok_in = (ns_in is True) or (ns_in is None)
                        if ok_out and ok_in:
                            tmp.append(t)
                    trips = tmp

                trips = [t for t in trips if (getattr(t.inbound, "departureTime", None) and getattr(t.outbound, "departureTime", None) and ((t.inbound.departureTime.date() - t.outbound.departureTime.date()).days == dv))]
                trips = [t for t in trips if keep_by_weekday(getattr(t.outbound, "departureTime", None), weekday)]
                trips = [t for t in trips if keep_by_time_window(getattr(t.outbound, "departureTime", None), dep_after, dep_before)]
                trips = [t for t in trips if keep_by_time_window(getattr(t.outbound, "arrivalTime", None), arr_after, arr_before)]

                for t in trips:
                    out, inn = t.outbound, t.inbound
                    if price_max is not None:
                        tp = getattr(t, "totalPrice", None)
                        if not (isinstance(tp, (int,float)) and tp <= price_max):
                            continue
                    rows.append({
                        "PREZZO/PAX (TOT A/R)": getattr(t, "totalPrice", None),
                        "VALUTA": getattr(out, "currency", currency),
                        "OUT: PREZZO/PAX": getattr(out, "price", None),
                        "OUT: PARTENZA": getattr(out, "departureTime", None),
                        "OUT: ARRIVO": getattr(out, "arrivalTime", None),
                        "OUT: VOLO": getattr(out, "flightNumber", ""),
                        "IN: PREZZO/PAX": getattr(inn, "price", None),
                        "IN: PARTENZA": getattr(inn, "departureTime", None),
                        "IN: ARRIVO": getattr(inn, "arrivalTime", None),
                        "IN: VOLO": getattr(inn, "flightNumber", ""),
                        "ORIGINE": getattr(out, "origin", ""),
                        "DEST": getattr(out, "destination", ""),
                        "DURATA (gg)": dv,
                        "OUT: PARTENZA (IT)": fmt_it(getattr(out, "departureTime", None)),
                        "OUT: ARRIVO (IT)": fmt_it(getattr(out, "arrivalTime", None)),
                        "IN: PARTENZA (IT)": fmt_it(getattr(inn, "departureTime", None)),
                        "IN: ARRIVO (IT)": fmt_it(getattr(inn, "arrivalTime", None)),
                    })
                current += timedelta(days=step_days)
    return pd.DataFrame(rows)

# ---- Sidebar: parametri
st.sidebar.header("Parametri")
mode = st.sidebar.selectbox("Modalità", ["oneway","return","duration"])

# Toggle per usare la tendina aeroporti
use_picker = st.sidebar.checkbox("Scegli aeroporti da tendina (consigliato)")

if use_picker:
    origins_default = ["BGY","MXP"]
    origins = pick_airports_multiselect("origins_picker", origins_default)
    dest_single = pick_airport_single("dest_picker", None)
    dests_multi = parse_csv(st.sidebar.text_input("OPZIONALE: Dest multiple CSV (integra la tendina)", ""))
else:
    origins = parse_csv(st.sidebar.text_input("Origini (CSV)", "BGY,MXP"))
    dest_single_txt = st.sidebar.text_input("Dest singola (opzionale)", "")
    dest_single = dest_single_txt.strip().upper() or None
    dests_multi = parse_csv(st.sidebar.text_input("Dest multiple CSV (opzionale)", ""))

colp1, colp2 = st.sidebar.columns(2)
with colp1:
    adults = st.number_input("Adulti", 1, 10, 1)
with colp2:
    children = st.number_input("Bambini", 0, 10, 0)

nonstop = st.sidebar.checkbox("Solo diretti")
currency = st.sidebar.selectbox("Valuta", ["EUR","GBP","USD"], index=0)
price_max_val = st.sidebar.number_input("Prezzo max / pax (0 = nessun limite)", 0, 10000, 0)
price_max = None if price_max_val == 0 else float(price_max_val)

weekday = st.sidebar.multiselect("Giorni di partenza (IT)", IT_DOW, [])
dep_after = st.sidebar.time_input("Partenza dopo (>=)", value=time(0,0))
dep_before = st.sidebar.time_input("Partenza prima (<=)", value=time(23,59))
arr_after = st.sidebar.time_input("Arrivo dopo (>=)", value=time(0,0))
arr_before = st.sidebar.time_input("Arrivo prima (<=)", value=time(23,59))

# Date per modalità
today = date.today()
if mode == "oneway":
    start = st.sidebar.date_input("Inizio", today)
    end = st.sidebar.date_input("Fine", today + timedelta(days=30))
elif mode == "return":
    ob_start = st.sidebar.date_input("Inizio ANDATA", today)
    ob_end = st.sidebar.date_input("Fine ANDATA", today + timedelta(days=15))
    ib_start = st.sidebar.date_input("Inizio RITORNO", today + timedelta(days=3))
    ib_end = st.sidebar.date_input("Fine RITORNO", today + timedelta(days=30))
else:
    start = st.sidebar.date_input("Inizio ricerca", today)
    end = st.sidebar.date_input("Fine ricerca", today + timedelta(days=60))
    dur_kind = st.sidebar.selectbox("Durata", ["Singola","Forchetta"])
    if dur_kind == "Singola":
        days_values = [st.sidebar.number_input("Giorni (esatti)", 1, 30, 4)]
    else:
        dmin = st.sidebar.number_input("Giorni min", 1, 30, 4)
        dmax = st.sidebar.number_input("Giorni max", int(dmin), 60, max(int(dmin),6))
        days_values = list(range(int(dmin), int(dmax)+1))
    step_days = int(st.sidebar.number_input("Step tra partenze (giorni)", 1, 14, 1))

sort_by = st.selectbox("Ordina per", ["departure","price_each","total_price_each","group_total"])
limit = st.number_input("Limite righe (0 = nessun limite)", 0, 5000, 0)

go = st.button("🔎 Cerca voli")

def sort_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if sort_by == "departure":
        key = "PARTENZA" if "PARTENZA" in df.columns else ("OUT: PARTENZA" if "OUT: PARTENZA" in df.columns else df.columns[0])
        return df.sort_values(by=key, ascending=True, kind="mergesort")
    if sort_by == "price_each":
        key = "PREZZO/PAX" if "PREZZO/PAX" in df.columns else "OUT: PREZZO/PAX"
        return df.sort_values(by=key, ascending=True, na_position="last", kind="mergesort")
    if sort_by == "total_price_each":
        key = "PREZZO/PAX (TOT A/R)" if "PREZZO/PAX (TOT A/R)" in df.columns else "PREZZO/PAX"
        return df.sort_values(by=key, ascending=True, na_position="last", kind="mergesort")
    if sort_by == "group_total":
        key = "TOT STIM. GRUPPO" if "TOT STIM. GRUPPO" in df.columns else "TOT STIM."
        if key in df.columns:
            return df.sort_values(by=key, ascending=True, na_position="last", kind="mergesort")
    return df

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return bio.getvalue()

if go:
    if not origins:
        st.warning("Inserisci almeno una origine (o selezionala dalla tendina).")
        st.stop()

    with st.spinner("Cerco i voli…"):
        if mode == "oneway":
            df = search_oneway(origins, dest_single, dests_multi, start, end, currency, adults, children,
                               nonstop, price_max, weekday, dep_after, dep_before, arr_after, arr_before)
        elif mode == "return":
            df = search_return(origins, dest_single, dests_multi, ob_start, ob_end, ib_start, ib_end,
                               currency, adults, children, nonstop, price_max, weekday, dep_after, dep_before, arr_after, arr_before)
            # calcola TOT STIM. GRUPPO se possibile
            if not df.empty and "PREZZO/PAX (TOT A/R)" in df.columns:
                pax = adults + children
                df["TOT STIM. GRUPPO"] = df["PREZZO/PAX (TOT A/R)"].apply(lambda x: x*pax if pd.notnull(x) else None)
        else:
            df = search_duration(origins, dest_single, dests_multi, start, end, days_values, step_days,
                                 currency, adults, children, nonstop, price_max, weekday, dep_after, dep_before, arr_after, arr_before)
            if not df.empty and "PREZZO/PAX (TOT A/R)" in df.columns:
                pax = adults + children
                df["TOT STIM. GRUPPO"] = df["PREZZO/PAX (TOT A/R)"].apply(lambda x: x*pax if pd.notnull(x) else None)

    df = sort_df(df)
    if limit and limit > 0:
        df = df.head(int(limit))

    st.success(f"Trovate {len(df)} soluzioni.")
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("⬇️ CSV", to_csv_bytes(df), file_name="ryanair_risultati.csv", mime="text/csv")
        with c2:
            st.download_button("⬇️ XLSX", to_xlsx_bytes(df), file_name="ryanair_risultati.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("""
---
**Suggerimenti**
- Per avere la lista completa degli aeroporti, aggiungi un file `airports.csv` (colonne: `IATA,City,Airport,Country`) nella root dell'app. Verrà caricato automaticamente.
- Il filtro *Solo diretti* dipende dai dati esposti dall'API: se i segmenti non sono disponibili, alcuni voli con scalo potrebbero rimanere nei risultati.
""")