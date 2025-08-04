from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from forexconnect import ForexConnect
import datetime
import json
from typing import Optional, List
import requests
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
    """Mengambil data history dari ForexConnect"""
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
    """Ambil data forex multi-timeframe"""
    try:
        with ForexConnect() as fx:
            print(f"Connecting to {request.connection} account...")
            
            fx.login(
                request.username, 
                request.password, 
                request.url, 
                request.connection, 
                None, 
                None, 
                on_session_status_changed
            )
            print("Login successful!")

            print(f"Fetching data for {request.instrument}...")
            
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
            print("Logged out successfully")
        except Exception as e:
            print(f"Error during logout: {str(e)}")

# ==========================
# Forex Factory Calendar Section
# ==========================
@app.get("/get-economic-calendar")
async def get_economic_calendar(currencies: Optional[List[str]] = None, impact: str = "High"):
    """
    Ambil data kalender ekonomi dari Forex Factory (via JS object)
    :param currencies: ["USD","EUR"]
    :param impact: High / Medium / Low
    """
    try:
        url = "https://www.forexfactory.com/calendar"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        html = response.text

        # Cari JS object window.calendarComponentStates
        match = re.search(r'window\.calendarComponentStates\s*=\s*({.*});', html)
        if not match:
            raise HTTPException(status_code=500, detail="Tidak menemukan data kalender")

        raw_json = match.group(1)
        # Perbaiki key supaya bisa parse
        raw_json = re.sub(r'(\d+):', r'"\1":', raw_json)  # ubah key angka ke string
        data = json.loads(raw_json)

        today_events = []
        for day in data["1"]["days"]:
            for ev in day.get("events", []):
                event_currency = ev.get("currency", "")
                event_impact = ev.get("impactTitle", "")
                if impact in event_impact and (not currencies or event_currency in currencies):
                    today_events.append({
                        "time": ev.get("timeLabel", ""),
                        "currency": event_currency,
                        "impact": event_impact,
                        "event": ev.get("name", ""),
                        "forecast": ev.get("forecast", ""),
                        "actual": ev.get("actual", ""),
                        "date": ev.get("date", "")
                    })

        return {"status": "success", "events": today_events}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic calendar: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)
