import streamlit as st
import pandas as pd
from datetime import date, time, timedelta
from typing import List, Optional
import io

st.set_page_config(page_title="Ryanair Finder", page_icon="✈️", layout="wide")
st.title("✈️ Ryanair Finder (Web)")
st.caption("Basato su ryanair-py • origini/destinazioni multiple • diretti • filtri prezzo/giorni/orari • export CSV/XLSX")

# --- Import libreria con messaggio chiaro se manca
try:
    from ryanair import Ryanair
except Exception as e:
    st.error("Impossibile importare 'ryanair'. Installa il pacchetto 'ryanair-py' (requirements.txt).")
    st.stop()

# -------------------- Utils --------------------
IT_DOW = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

def fmt_it(dt):
    if not dt:
        return ""
    try:
        w = IT_DOW[dt.weekday()]
        return f"{w} {dt.day:02d}/{dt.month:02d}/{dt.year} {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return str(dt)

def parse_list_csv(csv_str: str) -> List[str]:
    if not csv_str:
        return []
    return [x.strip().upper() for x in csv_str.split(",") if x.strip()]

def is_nonstop_leg(obj) -> Optional[bool]:
    # prova varie convenzioni esposte dalla libreria
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
    return None  # sconosciuto

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
    """
    Alcune versioni di ryanair-py non supportano adults/children nel costruttore.
    Fallback automatico per evitare TypeError.
    """
    try:
        return Ryanair(currency=currency, adults=adults, children=children)
    except TypeError:
        return Ryanair(currency=currency)

# -------------------- Ricerca --------------------
@st.cache_data(show_spinner=True)
def search_oneway(origins: List[str], dests: List[str], start: date, end: date,
                  adults: int, children: int, nonstop: bool, price_max: Optional[float],
                  weekdays: List[str], dep_after: Optional[time], dep_before: Optional[time],
                  arr_after: Optional[time], arr_before: Optional[time], currency: str) -> pd.DataFrame:
    api = build_api(currency, adults, children)
    rows = []
    for origin in origins:
        flights = api.get_cheapest_flights(origin, start, end)

        # filtra destinazioni (se presenti)
        if dests:
            flights = [f for f in flights if getattr(f, "destination", "").upper() in dests]

        # solo diretti (se l'API lo segnala; se sconosciuto teniamo il volo)
        if nonstop:
            filtered = []
            for f in flights:
                ns = is_nonstop_leg(f)
                if ns is True or ns is None:
                    filtered.append(f)
            flights = filtered

        # prezzo max per pax
        if price_max not in (None, 0):
            flights = [f for f in flights if isinstance(getattr(f, "price", None), (int, float)) and f.price <= price_max]

        # giorni/orari partenza + orari arrivo
        flights = [f for f in flights if keep_by_weekday(getattr(f, "departureTime", None), weekdays)]
        flights = [f for f in flights if keep_by_time_window(getattr(f, "departureTime", None), dep_after, dep_before)]
        flights = [f for f in flights if keep_by_time_window(getattr(f, "arrivalTime", None), arr_after, arr_before)]

        # output
        for f in flights:
            rows.append(dict(
                PREZZO_PAX=getattr(f, "price", None),
                VALUTA=getattr(f, "currency", currency),
                ORIGINE=getattr(f, "origin", ""),
                DEST=getattr(f, "destination", ""),
                PARTENZA=getattr(f, "departureTime", None),
                ARRIVO=getattr(f, "arrivalTime", None),
                VOLO=getattr(f, "flightNumber", ""),
                PARTENZA_IT=fmt_it(getattr(f, "departureTime", None)),
                ARRIVO_IT=fmt_it(getattr(f, "arrivalTime", None)),
            ))
    df = pd.DataFrame(rows)
    # ordina per partenza di default
    if not df.empty and "PARTENZA" in df.columns:
        df = df.sort_values(by="PARTENZA", ascending=True, kind="mergesort")
    return df

# -------------------- UI --------------------
mode = st.sidebar.radio("Modalità", ["oneway"], index=0)

with st.sidebar:
    origins = parse_list_csv(st.text_input("Origini (CSV)", "BGY,MXP"))
    dests = parse_list_csv(st.text_input("Destinazioni (CSV, opzionale)", ""))

    start = st.date_input("Data inizio", value=date.today())
    end = st.date_input("Data fine", value=date.today() + timedelta(days=30))

    col_a, col_b = st.columns(2)
    with col_a:
        adults = st.number_input("Adulti", 1, 9, 1)
    with col_b:
        children = st.number_input("Bambini", 0, 9, 0)

    nonstop = st.checkbox("Solo diretti", value=False)
    price_max_val = st.number_input("Prezzo massimo/pax (€) — 0 = nessun limite", 0, 10000, 0)
    price_max = None if price_max_val == 0 else float(price_max_val)

    weekdays = st.multiselect("Giorni di partenza", IT_DOW, [])
    dep_after = st.time_input("Partenza dopo (>=)", value=time(0, 0))
    dep_before = st.time_input("Partenza prima (<=)", value=time(23, 59))
    arr_after = st.time_input("Arrivo dopo (>=)", value=time(0, 0))
    arr_before = st.time_input("Arrivo prima (<=)", value=time(23, 59))

    currency = st.selectbox("Valuta", ["EUR", "GBP", "USD"], index=0)

    run = st.button("🔎 Cerca")

if run:
    if not origins:
        st.warning("Inserisci almeno un aeroporto di partenza (Origini).")
        st.stop()

    if mode == "oneway":
        df = search_oneway(
            origins, dests, start, end, adults, children,
            nonstop, price_max, weekdays, dep_after, dep_before,
            arr_after, arr_before, currency
        )
        st.success(f"{len(df)} voli trovati")
        st.dataframe(df, use_container_width=True)

        if not df.empty:
            # CSV
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Scarica CSV", csv_bytes, file_name="voli.csv", mime="text/csv")

            # XLSX in memoria (fix: non scrivere su disco, ma BytesIO)
            xlsx_buf = io.BytesIO()
            with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False)
            st.download_button(
                "⬇️ Scarica XLSX",
                xlsx_buf.getvalue(),
                file_name="voli.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

st.markdown("""
---
**Note**
- Prezzi e disponibilità sono indicativi e possono variare rapidamente. Verifica sempre su sito/app Ryanair.
- Il filtro *Solo diretti* viene applicato se l'API fornisce abbastanza dettagli sui segmenti; in caso contrario alcuni voli con scalo potrebbero non essere esclusi.
""")