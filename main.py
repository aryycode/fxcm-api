import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from forexconnect import ForexConnect
import datetime
import json
from typing import Optional, List
import cloudscraper
import re

app = FastAPI(title="Forex Data & Calendar API", description="Ambil data forex multi-timeframe + kalender ekonomi")

# ==========================
# Forex Data Section
# ==========================
class ForexRequest(BaseModel):
    username: str
    password: str
    url: str = "http://www.fxcorporate.com/Hosts.jsp"
    connection: str = "Real"
    instrument: str = "GBP/USD"
    candles_d1: Optional[int] = 60
    candles_h4: Optional[int] = 100
    candles_h1: Optional[int] = 150
    candles_m15: Optional[int] = 300
    candles_m5: Optional[int] = 400
    candles_m1: Optional[int] = 750

def on_session_status_changed(session, status):
    print(f"Session: {session}, Status: {status}")

def get_history(fx, instrument, timeframe, count):
    try:
        history = fx.get_history(instrument, timeframe, quotes_count=count)
        data = []
        for row in history:
            data.append({
                "time": str(row['Date']),
                "open": round(row['BidOpen'], 5),
                "high": round(row['BidHigh'], 5),
                "low": round(row['BidLow'], 5),
                "close": round(row['BidClose'], 5)
            })
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting {timeframe} data: {str(e)}")

@app.get("/")
async def root():
    return {
        "message": "Forex Data & Calendar API is running",
        "endpoints": ["/get-forex-data", "/get-economic-calendar"]
    }

@app.post("/get-forex-data")
async def get_forex_data(request: ForexRequest):
    try:
        with ForexConnect() as fx:
            fx.login(
                request.username,
                request.password,
                request.url,
                request.connection,
                None,
                None,
                on_session_status_changed
            )
            data = {
                "instrument": request.instrument,
                "timestamp": datetime.datetime.now().isoformat(),
                "daily": get_history(fx, request.instrument, "D1", request.candles_d1),
                "H4": get_history(fx, request.instrument, "H4", request.candles_h4),
                "H1": get_history(fx, request.instrument, "H1", request.candles_h1),
                "M15": get_history(fx, request.instrument, "m15", request.candles_m15),
                "M5": get_history(fx, request.instrument, "m5", request.candles_m5),
                "M1": get_history(fx, request.instrument, "m1", request.candles_m1)
            }
            return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch forex data: {str(e)}")
    finally:
        try:
            fx.logout()
        except:
            pass

# ==========================
# Forex Factory Scraper
# ==========================
@app.get("/get-economic-calendar")
async def get_economic_calendar(currencies: Optional[List[str]] = None, impact: str = "High"):
    """
    Ambil data kalender ekonomi dari ForexFactory (dari script JSON di halaman).
    Filter by currencies (contoh: USD, GBP) dan impact level (Low, Medium, High).
    """
    try:
        scraper = cloudscraper.create_scraper()
        url = "https://www.forexfactory.com/calendar"
        html = scraper.get(url).text

        # Cari JSON dari script menggunakan regex
        match = re.search(r'window\.calendarComponentStates\s*=\s*(\{.*?\});', html, re.S)
        if not match:
            raise HTTPException(status_code=500, detail="Tidak menemukan data kalender di halaman")

        raw_json = match.group(1)

        # Bersihkan trailing karakter dan parse JSON
        # Ganti single quote -> double quote agar valid JSON
        raw_json = raw_json.replace("'", '"')
        data = json.loads(raw_json)

        # Ambil daftar hari dan event
        days = data.get("1", {}).get("days", [])
        events = []
        for day in days:
            for ev in day.get("events", []):
                event_currency = ev.get("currency", "")
                event_impact = ev.get("impactName", "")
                if impact.lower() in event_impact.lower() and (not currencies or event_currency in currencies):
                    events.append({
                        "date": day.get("date", ""),
                        "time": ev.get("timeLabel", ""),
                        "currency": event_currency,
                        "impact": event_impact,
                        "event": ev.get("name", ""),
                        "forecast": ev.get("forecast", ""),
                        "actual": ev.get("actual", ""),
                        "previous": ev.get("previous", "")
                    })

        return {"status": "success", "events": events}

    except Exception as e:
        print(f"Error scraping Forex Factory: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic calendar: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)
