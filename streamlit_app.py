import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
from ryanair import Ryanair

# -------------------- Utils --------------------
IT_DOW = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

def fmt_it(dt):
    if not dt:
        return ""
    w = IT_DOW[dt.weekday()]
    return f"{w} {dt.day:02d}/{dt.month:02d}/{dt.year} {dt.hour:02d}:{dt.minute:02d}"

def parse_list_csv(csv_str):
    if not csv_str:
        return []
    return [x.strip().upper() for x in csv_str.split(",") if x.strip()]

def is_nonstop_leg(obj):
    if hasattr(obj, "stops"):
        try:
            return int(getattr(obj, "stops")) == 0
        except:
            pass
    if hasattr(obj, "isDirect"):
        val = getattr(obj, "isDirect")
        if isinstance(val, bool):
            return val
    segs = getattr(obj, "segments", None)
    if isinstance(segs, (list, tuple)):
        return len(segs) <= 1
    return None

def keep_by_weekday(dt, weekdays):
    if not weekdays: return True
    if not dt: return True
    it = IT_DOW[dt.weekday()]
    return it in weekdays

def keep_by_time_window(dt, after, before):
    if not dt: return True
    t = dt.time()
    if after and t < after: return False
    if before and t > before: return False
    return True

# -------------------- Ricerca --------------------
@st.cache_data(show_spinner=False)
def search_oneway(origins, dests, start, end, adults, children,
                  nonstop, price_max, weekdays, after, before,
                  arrive_after, arrive_before, currency):
    api = Ryanair(currency=currency, adults=adults, children=children)
    rows = []
    for origin in origins:
        flights = api.get_cheapest_flights(origin, start, end)
        flights = [f for f in flights if (not dests or f.destination.upper() in dests)]
        if nonstop:
            flights = [f for f in flights if (is_nonstop_leg(f) is True or is_nonstop_leg(f) is None)]
        if price_max:
            flights = [f for f in flights if f.price <= price_max]
        flights = [f for f in flights if keep_by_weekday(f.departureTime, weekdays)]
        flights = [f for f in flights if keep_by_time_window(f.departureTime, after, before)]
        flights = [f for f in flights if keep_by_time_window(f.arrivalTime, arrive_after, arrive_before)]
        for f in flights:
            rows.append(dict(
                prezzo=f.price,
                valuta=f.currency,
                origine=f.origin,
                dest=f.destination,
                partenza=fmt_it(f.departureTime),
                arrivo=fmt_it(f.arrivalTime),
                volo=f.flightNumber
            ))
    return pd.DataFrame(rows)

# -------------------- UI --------------------
st.set_page_config(page_title="Ryanair Finder", layout="wide")
st.title("✈️ Ryanair Finder (Web)")

mode = st.sidebar.radio("Modalità", ["oneway"], index=0)

with st.sidebar:
    origins = st.text_input("Origini (CSV)", "BGY,MXP").upper().split(",")
    dests = st.text_input("Destinazioni (CSV, opzionale)", "").upper().split(",") if st.text_input else []
    start = st.date_input("Data inizio", value=date.today())
    end = st.date_input("Data fine", value=date.today() + timedelta(days=30))
    adults = st.number_input("Adulti", 1, 9, 1)
    children = st.number_input("Bambini", 0, 9, 0)
    nonstop = st.checkbox("Solo diretti")
    price_max = st.number_input("Prezzo massimo/pax (€)", 0, 1000, 0)
    weekdays = st.multiselect("Giorni partenza", IT_DOW, [])
    after = st.time_input("Partenza dopo", None, step=900, key="after")
    before = st.time_input("Partenza prima", None, step=900, key="before")
    arrive_after = st.time_input("Arrivo dopo", None, step=900, key="arr_after")
    arrive_before = st.time_input("Arrivo prima", None, step=900, key="arr_before")
    currency = st.selectbox("Valuta", ["EUR","GBP","USD"], index=0)
    run = st.button("Cerca")

if run:
    if mode == "oneway":
        df = search_oneway(origins, dests, start, end, adults, children,
                           nonstop, price_max, weekdays, after, before,
                           arrive_after, arrive_before, currency)
        st.success(f"{len(df)} voli trovati")
        st.dataframe(df)
        if not df.empty:
            st.download_button("💾 Scarica CSV", df.to_csv(index=False).encode("utf-8"),
                               file_name="voli.csv", mime="text/csv")
            st.download_button("📊 Scarica Excel", df.to_excel("voli.xlsx", index=False, engine="openpyxl"),
                               file_name="voli.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")