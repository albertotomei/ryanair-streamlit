import streamlit as st
import pandas as pd
from datetime import date, time, timedelta
from typing import List, Optional
import io
import os

st.set_page_config(page_title="Ryanair Finder (Duration A/R)", page_icon="✈️", layout="wide")
st.title("✈️ Ryanair Finder — Duration (A/R) di default")
st.caption("ryanair-py • durata fissa/forchetta • multi origini/destinazioni • diretti • giorni/orari • prezzo • export")

# ---------- Libreria backend con fallback costruttore ----------
try:
    from ryanair import Ryanair
except Exception:
    st.error("Impossibile importare 'ryanair'. Aggiungi il pacchetto 'ryanair-py' in requirements.txt.")
    st.stop()

def build_api(currency: str, adults: int, children: int):
    try:
        return Ryanair(currency=currency, adults=adults, children=children)
    except TypeError:
        return Ryanair(currency=currency)

# ---------- Utilità ----------
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

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return bio.getvalue()

# ---------- Aeroporti da CSV (obbligatorio) ----------
CSV_PATH = "airports.csv"  # metti qui il tuo file ordinato per città
if not os.path.exists(CSV_PATH):
    st.error("File 'airports.csv' non trovato. Mettilo nella stessa cartella dell'app.")
    st.stop()

air_df = pd.read_csv(CSV_PATH)
if not {"IATA","City","Airport","Country"}.issubset(air_df.columns):
    st.error("Il CSV deve avere le colonne: IATA,City,Airport,Country")
    st.stop()

# ordina per City (se non già ordinato)
air_df = air_df.sort_values(by=["City","Airport","IATA"]).reset_index(drop=True)
air_records = air_df.to_dict(orient="records")
label_map = {
    r["IATA"].upper(): f"{r['City']} – {r['Airport']} ({r['IATA'].upper()}) · {r['Country']}"
    for r in air_records
}
all_iata = list(label_map.keys())

def multiselect_airports(label: str, key: str, default_codes: List[str]) -> List[str]:
    options = all_iata
    fmt = lambda iata: label_map.get(iata, iata)
    # Preselezione se codice presente in lista
    defaults = [c for c in default_codes if c in options]
    return st.multiselect(label, options=options, default=defaults, format_func=fmt, key=key)

def select_optional_airport(label: str, key: str) -> Optional[str]:
    options = ["(Nessuna)"] + all_iata
    fmt = lambda x: "(Nessuna)" if x == "(Nessuna)" else label_map.get(x, x)
    sel = st.selectbox(label, options=options, index=0, format_func=fmt, key=key)
    return None if sel == "(Nessuna)" else sel

# ---------- Sidebar (DEFAULT = DURATION) ----------
st.sidebar.header("Parametri ricerca (A/R duration di default)")

# Origini/Destinazioni
origins = multiselect_airports("Origini (multi)", "origins", default_codes=["FCO"])  # default FCO come tuo esempio
dest_single = select_optional_airport("Destinazione (singola, opzionale)", "dest_single")
dests_multi = multiselect_airports("Destinazioni (multiple, opzionali)", "dests_multi", default_codes=["BVA"])

# Passeggeri, valuta, diretti, prezzo
col_p1, col_p2 = st.sidebar.columns(2)
with col_p1:
    adults = st.number_input("Adulti", 1, 10, 2)       # default 2 come esempio
with col_p2:
    children = st.number_input("Bambini", 0, 10, 2)    # default 2 come esempio

nonstop = st.sidebar.checkbox("Solo diretti", value=True)
currency = st.sidebar.selectbox("Valuta", ["EUR","GBP","USD","PLN","RON","HUF","CZK"], index=0)
price_max_val = st.sidebar.number_input("Prezzo max / pax (0 = nessun limite)", 0, 10000, 100)  # default 100 come esempio
price_max = None if price_max_val == 0 else float(price_max_val)

# Giorni e fasce orarie (partenza outbound; arrivo outbound)
weekday = st.sidebar.multiselect("Giorni di partenza (IT)", IT_DOW, default=[])
dep_after = st.sidebar.time_input("Partenza dopo (>=)", value=time(0,0))
dep_before = st.sidebar.time_input("Partenza prima (<=)", value=time(23,59))
arr_after = st.sidebar.time_input("Arrivo dopo (>=)", value=time(0,0))
arr_before = st.sidebar.time_input("Arrivo prima (<=)", value=time(23,59))

# Finestra temporale + durata
today = date.today()
start = st.sidebar.date_input("Inizio ricerca", date(2025,10,1))     # default come tuo esempio
end   = st.sidebar.date_input("Fine ricerca",   date(2026,5,31))     # default come tuo esempio

dur_kind = st.sidebar.selectbox("Durata", ["Singola","Forchetta"], index=0)
if dur_kind == "Singola":
    days_values = [st.sidebar.number_input("Giorni (esatti)", 1, 30, 3)]  # default 3 come esempio
else:
    dmin = st.sidebar.number_input("Giorni min", 1, 30, 3)
    dmax = st.sidebar.number_input("Giorni max", int(dmin), 60, max(int(dmin), 6))
    days_values = list(range(int(dmin), int(dmax)+1))

step_days = int(st.sidebar.number_input("Step tra partenze (giorni)", 1, 14, 1))  # default 1 come esempio

# Ordinamento + limite
sort_by = st.selectbox("Ordina per", ["departure","price_each","total_price_each","group_total"], index=0)
limit = st.number_input("Limite righe (0 = nessun limite)", 0, 10000, 0)

go = st.button("🔎 Cerca (A/R duration)")

# ---------- Ricerca Duration (replica CLI) ----------
@st.cache_data(show_spinner=True)
def search_duration(
    origins: List[str], dest_single: Optional[str], dests_multi: List[str],
    start: date, end: date, days_values: List[int], step_days: int,
    currency: str, adults: int, children: int,
    nonstop: bool, price_max: Optional[float],
    weekday: List[str], dep_after: Optional[time], dep_before: Optional[time],
    arr_after: Optional[time], arr_before: Optional[time]
) -> pd.DataFrame:

    api = build_api(currency, adults, children)
    rows = []

    def match_dest(code: str) -> bool:
        code = (code or "").upper()
        if dest_single:
            return code == dest_single.upper()
        return (not dests_multi) or (code in dests_multi)

    for origin in origins:
        for dv in days_values:
            stay = timedelta(days=dv)
            last_departure = end - stay
            current = start
            while current <= last_departure:
                out_start = out_end = current
                in_start = in_end = current + stay

                trips = api.get_cheapest_return_flights(origin, out_start, out_end, in_start, in_end)
                # filtri rotta
                trips = [t for t in trips if match_dest(getattr(t.outbound, "destination", ""))]

                # diretti (se info disponibile; se ignota, non escludo)
                if nonstop:
                    tmp = []
                    for t in trips:
                        ns_out = is_nonstop_leg(t.outbound)
                        ns_in  = is_nonstop_leg(t.inbound)
                        ok_out = (ns_out is True) or (ns_out is None)
                        ok_in  = (ns_in  is True) or (ns_in  is None)
                        if ok_out and ok_in:
                            tmp.append(t)
                    trips = tmp

                # durata esatta (per sicurezza)
                trips = [
                    t for t in trips
                    if getattr(t.inbound, "departureTime", None)
                    and getattr(t.outbound, "departureTime", None)
                    and ((t.inbound.departureTime.date() - t.outbound.departureTime.date()).days == dv)
                ]

                # weekday/orari su OUTBOUND (partenza e arrivo)
                trips = [t for t in trips if keep_by_weekday(getattr(t.outbound, "departureTime", None), weekday)]
                trips = [t for t in trips if keep_by_time_window(getattr(t.outbound, "departureTime", None), dep_after, dep_before)]
                trips = [t for t in trips if keep_by_time_window(getattr(t.outbound, "arrivalTime", None),  arr_after, arr_before)]

                # prezzo max per pax sul totale A/R
                if price_max is not None:
                    trips = [
                        t for t in trips
                        if isinstance(getattr(t, "totalPrice", None), (int,float))
                        and t.totalPrice <= price_max
                    ]

                # output righe
                pax = adults + children
                for t in trips:
                    out, inn = t.outbound, t.inbound
                    price_each_total = getattr(t, "totalPrice", None)
                    rows.append({
                        "PREZZO/PAX (TOT A/R)": price_each_total,
                        "VALUTA": getattr(out, "currency", currency),
                        "PAX (A+B)": f"{adults}+{children}",
                        "TOT STIM. GRUPPO": (price_each_total or 0) * pax if isinstance(price_each_total, (int,float)) else None,
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

    df = pd.DataFrame(rows)
    return df

def sort_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if sort_by == "departure":
        key = "OUT: PARTENZA" if "OUT: PARTENZA" in df.columns else df.columns[0]
        return df.sort_values(by=key, ascending=True, kind="mergesort")
    if sort_by == "price_each":
        key = "OUT: PREZZO/PAX" if "OUT: PREZZO/PAX" in df.columns else "PREZZO/PAX (TOT A/R)"
        return df.sort_values(by=key, ascending=True, na_position="last", kind="mergesort")
    if sort_by == "total_price_each":
        key = "PREZZO/PAX (TOT A/R)" if "PREZZO/PAX (TOT A/R)" in df.columns else "OUT: PREZZO/PAX"
        return df.sort_values(by=key, ascending=True, na_position="last", kind="mergesort")
    if sort_by == "group_total":
        key = "TOT STIM. GRUPPO"
        if key in df.columns:
            return df.sort_values(by=key, ascending=True, na_position="last", kind="mergesort")
    return df

# ---------- Azione ----------
if go:
    if not origins:
        st.warning("Seleziona almeno una origine.")
        st.stop()

    # se c'è dest singola la aggiungo alle multiple (come in CLI: filtro su singola o su lista)
    dests_filter = list(set(dests_multi + ([dest_single] if dest_single else [])))

    with st.spinner("Cerco combinazioni A/R migliori…"):
        df = search_duration(
            origins, dest_single, dests_filter,
            start, end, days_values, step_days,
            currency, adults, children,
            nonstop, price_max,
            weekday, dep_after, dep_before,
            arr_after, arr_before
        )

    df = sort_df(df)
    if limit and limit > 0:
        df = df.head(int(limit))

    st.success(f"Trovate {len(df)} soluzioni.")
    # Mostra campi chiave in testa
    preferred_cols = [
        "PREZZO/PAX (TOT A/R)","VALUTA","PAX (A+B)","TOT STIM. GRUPPO",
        "OUT: PREZZO/PAX","OUT: PARTENZA (IT)","OUT: ARRIVO (IT)","OUT: VOLO",
        "IN: PREZZO/PAX","IN: PARTENZA (IT)","IN: ARRIVO (IT)","IN: VOLO",
        "ORIGINE","DEST","DURATA (gg)"
    ]
    cols = [c for c in preferred_cols if c in df.columns] + [c for c in df.columns if c not in preferred_cols]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)

    if not df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("⬇️ CSV", to_csv_bytes(df), file_name="ryanair_duration.csv", mime="text/csv")
        with c2:
            st.download_button("⬇️ XLSX", to_xlsx_bytes(df), file_name="ryanair_duration.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("""
---
**Note**
- I risultati dipendono dai dati esposti da `ryanair-py`: *Solo diretti* viene applicato quando i segmenti/scali sono disponibili.
- I filtri Giorni/Orari si riferiscono alla **partenza e arrivo dell’andata (outbound)** come nella CLI.
- Default impostati come nel tuo esempio: `FCO → BVA`, `days=3`, `step=1`, `adults=2`, `children=2`, `nonstop=true`, `price_max=100`, periodo 2025-10-01 → 2026-05-31.
""")