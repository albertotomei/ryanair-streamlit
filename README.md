# ✈️ Ryanair Finder (Web)

Interfaccia web per cercare voli Ryanair, basata su [`ryanair-py`](https://pypi.org/project/ryanair-py/).

## 🚀 Funzionalità
- Ricerca **one-way** (estendibile a return/duration)
- Origini e destinazioni multiple
- Filtri: diretti, prezzo massimo, giorni della settimana, fascia oraria partenza/arrivo
- Esportazione risultati in **CSV** e **Excel**
- Interfaccia **Streamlit**

## 📦 Installazione locale
```bash
pip install -r requirements.txt
streamlit run app.py