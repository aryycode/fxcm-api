from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from forexconnect import ForexConnect
import datetime
import json
from typing import Optional, List
import cloudscraper
from bs4 import BeautifulSoup

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
    """
    Endpoint untuk mengambil data forex multi timeframe
    """
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

            print(f"Fetched data for {request.instrument}")
            
            return {"status": "success", "data": data}

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch forex data: {str(e)}")
    
    finally:
        try:
            fx.logout()
            print("Logged out successfully")
        except Exception as e:
            print(f"Error during logout: {str(e)}")

# ==========================
# Forex Factory Scraper Section
# ==========================
@app.get("/get-economic-calendar")
async def get_economic_calendar(currencies: Optional[List[str]] = None, impact: str = "High"):
    """
    Scrape kalender ekonomi dari Forex Factory
    :param currencies: List mata uang yang difilter (contoh: ["USD", "EUR"])
    :param impact: Level impact (Low, Medium, High)
    """
    try:
        scraper = cloudscraper.create_scraper()
        url = "https://forexfactory.com/calendar"
        html = scraper.get(url).text
        soup = BeautifulSoup(html, 'html.parser')

        events = []
        rows = soup.select('tr.calendar__row')
        for row in rows:
            time = row.select_one('td.calendar__time')
            currency = row.select_one('td.calendar__currency')
            impact_elem = row.select_one('td.calendar__impact span')
            event = row.select_one('td.calendar__event')
            forecast = row.select_one('td.calendar__forecast')
            actual = row.select_one('td.calendar__actual')

            if currency and impact_elem:
                event_impact = impact_elem.get('title', '')  # impact level dari attribute
                event_currency = currency.text.strip()
                if impact in event_impact and (not currencies or event_currency in currencies):
                    events.append({
                        "time": time.text.strip() if time else "",
                        "currency": event_currency,
                        "impact": event_impact,
                        "event": event.text.strip() if event else "",
                        "forecast": forecast.text.strip() if forecast else "",
                        "actual": actual.text.strip() if actual else ""
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
