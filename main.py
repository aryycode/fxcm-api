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
    try:
        scraper = cloudscraper.create_scraper(delay=10, browser='chrome')
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        html = scraper.get(url, headers=headers).text

        match = re.search(r'window\.calendarComponentStates\s*=\s*(\{.*\});', html, re.S)
        if not match:
            raise HTTPException(status_code=500, detail="Tidak menemukan data kalender")

        raw_json = match.group(1)

        # Bersihkan trailing semicolon
        if raw_json.endswith(";"):
            raw_json = raw_json[:-1]

        # Ubah key angka ke string
        raw_json = re.sub(r'(\d+):', r'"\1":', raw_json)

        # Potong sampai curly brace terakhir
        last_brace = raw_json.rfind("}")
        if last_brace != -1:
            raw_json = raw_json[:last_brace+1]

        # Parse JSON
        data = json.loads(raw_json)

        if "1" not in data:
            raise HTTPException(status_code=500, detail="Data hari ini tidak ditemukan (key '1')")

        calendar_data = data["1"]
        events = []
        for day in calendar_data.get("days", []):
            for ev in day.get("events", []):
                if impact.lower() in ev.get("impactName", "").lower() and (not currencies or ev.get("currency", "") in currencies):
                    events.append({
                        "date": day.get("date", ""),
                        "time": ev.get("timeLabel", ""),
                        "currency": ev.get("currency", ""),
                        "impact": ev.get("impactTitle", ""),
                        "event": ev.get("name", ""),
                        "forecast": ev.get("forecast", ""),
                        "actual": ev.get("actual", ""),
                        "previous": ev.get("previous", "")
                    })

        return {"status": "success", "events": events}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic calendar: {str(e)}")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)
