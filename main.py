from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from forexconnect import ForexConnect
import datetime
import json
from typing import Optional, List
import requests
import re
from urllib.parse import urlencode

app = FastAPI(title="Forex Data & Calendar API", description="Ambil data forex multi-timeframe + kalender ekonomi")

# TradingEconomics Configuration
TRADING_ECONOMICS_API_KEY = "38d77f8befa34eb:0ai5bv92c79e7jo"
TRADING_ECONOMICS_BASE_URL = "https://api.tradingeconomics.com"

# Currency to Country Mapping
CURRENCY_TO_COUNTRY = {
    # Major Currencies
    "USD": "united states",
    "EUR": "euro area",
    "GBP": "united kingdom", 
    "JPY": "japan",
    "CHF": "switzerland",
    "CAD": "canada",
    "AUD": "australia",
    "NZD": "new zealand",
    
    # Other Major Currencies
    "CNY": "china",
    "CNH": "china",  # Offshore Chinese Yuan
    "HKD": "hong kong",
    "SGD": "singapore",
    "KRW": "south korea",
    "INR": "india",
    "MXN": "mexico",
    "BRL": "brazil",
    "ZAR": "south africa",
    "RUB": "russia",
    "TRY": "turkey",
    "NOK": "norway",
    "SEK": "sweden",
    "DKK": "denmark",
    "PLN": "poland",
    "CZK": "czech republic",
    "HUF": "hungary",
    
    # Commodities (Special handling)
    "XAU": "gold",  # Gold
    "XAG": "silver", # Silver
    "XPT": "platinum", # Platinum
    "XPD": "palladium", # Palladium
    
    # Additional currencies
    "THB": "thailand",
    "PHP": "philippines",
    "IDR": "indonesia",
    "MYR": "malaysia",
    "TWD": "taiwan",
    "VND": "vietnam",
    
    # Middle East & Africa
    "SAR": "saudi arabia",
    "AED": "united arab emirates",
    "QAR": "qatar",
    "KWD": "kuwait",
    "BHD": "bahrain",
    "OMR": "oman",
    "EGP": "egypt",
    "NGN": "nigeria",
    
    # Latin America
    "ARS": "argentina",
    "CLP": "chile",
    "COP": "colombia",
    "PEN": "peru",
    "UYU": "uruguay",
    
    # Eastern Europe
    "RON": "romania",
    "BGN": "bulgaria",
    "HRK": "croatia",
    "RSD": "serbia",
}

def parse_currency_input(currency_input: str) -> List[str]:
    """
    Parse currency input dan konversi ke country names
    Contoh: 
    - "USD" -> ["united states"]
    - "EUR,USD" -> ["euro area", "united states"]  
    - "XAU/USD" -> ["gold", "united states"]
    - "EURUSD" -> ["euro area", "united states"]
    """
    if not currency_input:
        return []
    
    # Clean input
    currency_input = currency_input.upper().strip()
    
    # Handle different formats
    currencies = []
    
    # Format: XAU/USD, EUR/USD, etc.
    if '/' in currency_input:
        parts = currency_input.split('/')
        currencies.extend(parts)
    
    # Format: EURUSD, GBPJPY, etc. (6 characters)
    elif len(currency_input) == 6 and currency_input.isalpha():
        currencies.append(currency_input[:3])  # First 3 chars
        currencies.append(currency_input[3:])  # Last 3 chars
    
    # Format: EUR,USD or EUR USD
    elif ',' in currency_input or ' ' in currency_input:
        separator = ',' if ',' in currency_input else ' '
        currencies = [c.strip() for c in currency_input.split(separator)]
    
    # Single currency: USD, EUR, etc.
    elif len(currency_input) == 3 and currency_input.isalpha():
        currencies.append(currency_input)
    
    # Convert currencies to countries
    countries = []
    for currency in currencies:
        currency = currency.strip().upper()
        if currency in CURRENCY_TO_COUNTRY:
            country = CURRENCY_TO_COUNTRY[currency]
            if country not in countries:  # Avoid duplicates
                countries.append(country)
    
    return countries

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
# TradingEconomics Calendar Section
# ==========================

def get_trading_economics_calendar(
    countries: Optional[List[str]] = None,
    importance: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Mengambil data kalender ekonomi dari TradingEconomics API
    """
    try:
        all_events = []
        
        # Jika ada multiple countries, ambil data untuk setiap country
        if countries and len(countries) > 1:
            for country in countries:
                try:
                    # Build URL parameters for each country
                    params = {
                        'c': TRADING_ECONOMICS_API_KEY,
                        'format': 'json'
                    }
                    
                    params['country'] = country
                    if importance:
                        params['importance'] = importance
                    if start_date:
                        params['d1'] = start_date
                    if end_date:
                        params['d2'] = end_date
                        
                    # Construct URL
                    url = f"{TRADING_ECONOMICS_BASE_URL}/calendar"
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json'
                    }
                    
                    # Make API request
                    response = requests.get(url, params=params, headers=headers, timeout=30)
                    if response.status_code == 200:
                        country_data = response.json()
                        if isinstance(country_data, list):
                            all_events.extend(country_data)
                        
                except Exception as e:
                    print(f"Error fetching data for {country}: {str(e)}")
                    continue
                    
            return all_events
            
        else:
            # Single country or no country filter
            params = {
                'c': TRADING_ECONOMICS_API_KEY,
                'format': 'json'
            }
            
            if countries and len(countries) == 1:
                params['country'] = countries[0]
            if importance:
                params['importance'] = importance
            if start_date:
                params['d1'] = start_date
            if end_date:
                params['d2'] = end_date
                
            # Construct URL
            url = f"{TRADING_ECONOMICS_BASE_URL}/calendar"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            # Make API request
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            return data
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"TradingEconomics API error: {str(e)}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse API response: {str(e)}")

@app.get("/get-economic-calendar")
async def get_economic_calendar(
    currencies: Optional[str] = Query(None, description="Currency codes separated by comma or forex pair (e.g., 'USD,EUR' or 'XAU/USD' or 'EURUSD')"),
    importance: Optional[str] = Query(None, description="Event importance: 1=Low, 2=Medium, 3=High"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD format)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD format)"),
    limit: Optional[int] = Query(100, description="Maximum number of events to return")
):
    """
    Ambil data kalender ekonomi dari TradingEconomics API
    
    Parameters:
    - currencies: Currency codes atau forex pairs (e.g., "USD", "EUR,USD", "XAU/USD", "EURUSD")
    - importance: Filter berdasarkan tingkat kepentingan 1-3 (opsional)
    - start_date: Tanggal mulai dalam format YYYY-MM-DD (opsional)
    - end_date: Tanggal akhir dalam format YYYY-MM-DD (opsional)
    - limit: Maksimal jumlah event yang dikembalikan
    
    Examples:
    /get-economic-calendar?currencies=USD&importance=3
    /get-economic-calendar?currencies=EUR,USD&start_date=2024-08-01
    /get-economic-calendar?currencies=XAU/USD&importance=3
    /get-economic-calendar?currencies=EURUSD&importance=2
    """
    try:
        # Parse currency input to get countries
        countries = []
        original_currencies = []
        
        if currencies:
            countries = parse_currency_input(currencies)
            original_currencies = currencies.upper().replace('/', ',').split(',') if currencies else []
            
            # Log the conversion for debugging
            print(f"Input currencies: {currencies}")
            print(f"Parsed countries: {countries}")
        
        # Jika tidak ada tanggal, gunakan hari ini sampai 7 hari ke depan
        if not start_date:
            start_date = datetime.datetime.now().strftime('%Y-%m-%d')
        if not end_date:
            end_date = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Get data from TradingEconomics
        raw_data = get_trading_economics_calendar(
            countries=countries if countries else None,
            importance=importance,
            start_date=start_date,
            end_date=end_date
        )
        
        # Sort events by date and time
        if isinstance(raw_data, list):
            raw_data.sort(key=lambda x: (x.get("Date", ""), x.get("Time", "")))
        
        # Process and format the data
        formatted_events = []
        for event in raw_data[:limit]:  # Limit results
            formatted_event = {
                "date": event.get("Date", ""),
                "time": event.get("Time", ""),
                "country": event.get("Country", ""),
                "category": event.get("Category", ""),
                "event": event.get("Event", ""),
                "reference": event.get("Reference", ""),
                "source": event.get("Source", ""),
                "sourceurl": event.get("SourceURL", ""),
                "actual": event.get("Actual", ""),
                "previous": event.get("Previous", ""),
                "forecast": event.get("Forecast", ""),
                "revised": event.get("Revised", ""),
                "importance": event.get("Importance", ""),
                "currency": event.get("Currency", ""),
                "unit": event.get("Unit", ""),
                "frequency": event.get("Frequency", ""),
                "calendarid": event.get("CalendarId", ""),
                "dateprecision": event.get("DatePrecision", "")
            }
            formatted_events.append(formatted_event)
        
        return {
            "status": "success",
            "total_events": len(formatted_events),
            "currency_mapping": {
                "input_currencies": currencies,
                "parsed_countries": countries,
                "supported_currencies": list(CURRENCY_TO_COUNTRY.keys()) if not currencies else None
            },
            "filters_applied": {
                "countries": countries,
                "importance": importance,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit
            },
            "events": formatted_events
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic calendar: {str(e)}")

@app.get("/get-economic-calendar/supported-currencies")
async def get_supported_currencies():
    """
    Mendapatkan daftar currency codes yang didukung dan mapping ke negara
    """
    return {
        "status": "success",
        "total_currencies": len(CURRENCY_TO_COUNTRY),
        "currency_mapping": CURRENCY_TO_COUNTRY,
        "examples": {
            "single_currency": "USD",
            "multiple_currencies": "EUR,USD", 
            "forex_pair_slash": "XAU/USD",
            "forex_pair_combined": "EURUSD"
        }
    }

@app.get("/get-economic-calendar/countries")
async def get_available_countries():
    """
    Mendapatkan daftar negara yang tersedia di TradingEconomics
    """
    try:
        url = f"{TRADING_ECONOMICS_BASE_URL}/calendar/country"
        params = {
            'c': TRADING_ECONOMICS_API_KEY,
            'format': 'json'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        countries = response.json()
        
        return {
            "status": "success",
            "total_countries": len(countries),
            "countries": countries
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch countries list: {str(e)}")

@app.get("/get-economic-calendar/indicators")
async def get_available_indicators(country: Optional[str] = Query(None, description="Filter indicators by country")):
    """
    Mendapatkan daftar indikator ekonomi yang tersedia
    """
    try:
        url = f"{TRADING_ECONOMICS_BASE_URL}/indicators"
        params = {
            'c': TRADING_ECONOMICS_API_KEY,
            'format': 'json'
        }
        
        if country:
            params['country'] = country
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        indicators = response.json()
        
        return {
            "status": "success",
            "total_indicators": len(indicators),
            "country_filter": country,
            "indicators": indicators
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch indicators list: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "timestamp": datetime.datetime.now().isoformat(),
        "trading_economics_configured": bool(TRADING_ECONOMICS_API_KEY)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)