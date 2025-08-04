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
# Forex Factory Scraper - SIMPLIFIED VERSION
# ==========================
def clean_json_string(raw_json):
    """
    Membersihkan string JSON dari ForexFactory
    """
    try:
        # Hapus whitespace di awal dan akhir
        raw_json = raw_json.strip()
        
        # Hapus trailing semicolon jika ada
        if raw_json.endswith(";"):
            raw_json = raw_json[:-1]
        
        # Hapus trailing comma sebelum closing brace/bracket
        raw_json = re.sub(r',(\s*[}\]])', r'\1', raw_json)
        
        # Convert numeric keys ke string keys
        raw_json = re.sub(r'(?<=[{,\s])(\d+)(?=\s*:)', r'"\1"', raw_json)
        
        # Fix undefined values
        raw_json = re.sub(r':\s*undefined\b', ': null', raw_json)
        
        return raw_json
        
    except Exception as e:
        raise Exception(f"Error cleaning JSON: {str(e)}")

def extract_calendar_json(html):
    """
    Ekstrak JSON data kalender dari HTML ForexFactory
    """
    # Find calendarComponentStates assignment
    start_pattern = r'window\.calendarComponentStates\s*='
    start_match = re.search(start_pattern, html)
    
    if not start_match:
        raise Exception("calendarComponentStates not found in HTML")
    
    start_pos = start_match.end()
    
    # Find opening brace
    brace_start = html.find('{', start_pos)
    if brace_start == -1:
        raise Exception("Opening brace not found")
    
    # Find matching closing brace using bracket counting
    brace_count = 0
    pos = brace_start
    
    while pos < len(html):
        char = html[pos]
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                # Found matching closing brace
                raw_json = html[brace_start:pos + 1]
                return raw_json
        pos += 1
    
    raise Exception("Matching closing brace not found")

@app.get("/get-economic-calendar")
async def get_economic_calendar(currencies: Optional[str] = None, impact: str = "High"):
    try:
        # Convert currencies string to list if provided
        currency_list = currencies.split(',') if currencies else None
        
        # Create scraper
        scraper = cloudscraper.create_scraper(delay=10)
        
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }
        
        print("Fetching ForexFactory calendar...")
        response = scraper.get(url, headers=headers, timeout=30)
        html = response.text
        
        print(f"HTML length: {len(html)}")
        print(f"Response status: {response.status_code}")
        
        # Extract JSON from HTML
        raw_json = extract_calendar_json(html)
        print(f"Raw JSON length: {len(raw_json)}")
        
        # Clean the JSON string
        cleaned_json = clean_json_string(raw_json)
        print(f"Cleaned JSON length: {len(cleaned_json)}")
        
        # Parse JSON
        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Error at position: {e.pos}")
            if e.pos < len(cleaned_json):
                context = cleaned_json[max(0, e.pos-50):e.pos+50]
                print(f"Context around error: {context}")
            raise HTTPException(status_code=500, detail=f"Error parsing JSON: {str(e)}")
        
        print(f"Parsed data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        # Find calendar data - try different possible keys
        calendar_data = None
        possible_keys = ["1", "0", "today", "calendar"]
        
        for key in possible_keys:
            if key in data:
                calendar_data = data[key]
                print(f"Found calendar data with key: {key}")
                break
        
        if not calendar_data:
            # If no specific key found, check if data itself has calendar structure
            if isinstance(data, dict) and "days" in data:
                calendar_data = data
                print("Using entire data structure as calendar data")
            else:
                available_keys = list(data.keys()) if isinstance(data, dict) else "No keys available"
                raise HTTPException(status_code=500, detail=f"Calendar data not found. Available keys: {available_keys}")
        
        # Extract events
        events = []
        days_data = calendar_data.get("days", [])
        
        if not days_data and isinstance(calendar_data, list):
            days_data = calendar_data
        
        print(f"Processing {len(days_data)} days of data")
        
        for day in days_data:
            if not isinstance(day, dict):
                continue
                
            day_events = day.get("events", [])
            day_date = day.get("date", "")
            
            for ev in day_events:
                if not isinstance(ev, dict):
                    continue
                
                event_impact = ev.get("impactTitle", ev.get("impact", "")).lower()
                event_currency = ev.get("currency", "")
                
                # Filter by impact
                if impact.lower() not in event_impact:
                    continue
                
                # Filter by currency if specified
                if currency_list and event_currency not in currency_list:
                    continue
                
                events.append({
                    "date": day_date,
                    "time": ev.get("timeLabel", ev.get("time", "")),
                    "currency": event_currency,
                    "impact": ev.get("impactTitle", ev.get("impact", "")),
                    "event": ev.get("name", ev.get("title", "")),
                    "forecast": ev.get("forecast", ""),
                    "actual": ev.get("actual", ""),
                    "previous": ev.get("previous", "")
                })
        
        print(f"Found {len(events)} matching events")
        
        return {
            "status": "success", 
            "events": events,
            "total_events": len(events),
            "filters": {
                "currencies": currency_list,
                "impact": impact
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic calendar: {str(e)}")

@app.get("/debug-calendar")
async def debug_calendar():
    """
    Endpoint untuk debugging ekstraksi data kalender
    """
    try:
        scraper = cloudscraper.create_scraper(delay=10)
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = scraper.get(url, headers=headers, timeout=30)
        html = response.text
        
        # Extract JSON
        try:
            raw_json = extract_calendar_json(html)
            cleaned_json = clean_json_string(raw_json)
            
            try:
                parsed_data = json.loads(cleaned_json)
                data_keys = list(parsed_data.keys()) if isinstance(parsed_data, dict) else "Not a dict"
                
                # Look for calendar structure
                calendar_info = {}
                if isinstance(parsed_data, dict):
                    for key, value in parsed_data.items()[:5]:  # Check first 5 keys only
                        if isinstance(value, dict) and 'days' in value:
                            days = value.get('days', [])
                            events_count = sum(len(day.get('events', [])) for day in days if isinstance(day, dict))
                            calendar_info[key] = {
                                'days_count': len(days),
                                'events_count': events_count
                            }
                
                return {
                    "status": "success",
                    "raw_json_length": len(raw_json),
                    "cleaned_json_length": len(cleaned_json),
                    "data_keys": data_keys,
                    "calendar_info": calendar_info,
                    "raw_preview": raw_json[:500],
                    "cleaned_preview": cleaned_json[:500]
                }
                
            except json.JSONDecodeError as e:
                return {
                    "status": "json_error",
                    "error": str(e),
                    "error_pos": e.pos,
                    "raw_json_length": len(raw_json),
                    "cleaned_json_length": len(cleaned_json),
                    "context_around_error": cleaned_json[max(0, e.pos-100):e.pos+100] if e.pos < len(cleaned_json) else "Position out of range",
                    "raw_preview": raw_json[:500],
                    "cleaned_preview": cleaned_json[:500]
                }
        
        except Exception as extraction_error:
            return {
                "status": "extraction_error",
                "error": str(extraction_error),
                "html_length": len(html),
                "calendarComponentStates_found": "calendarComponentStates" in html
            }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/test-scraper")
async def test_scraper():
    """
    Endpoint untuk testing scraper tanpa parsing data
    """
    try:
        scraper = cloudscraper.create_scraper(delay=10)
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = scraper.get(url, headers=headers, timeout=30)
        
        # Look for calendar data patterns
        patterns_found = {}
        patterns = [
            r'window\.calendarComponentStates',
            r'calendarComponentStates',
            r'calendar.*data',
            r'events.*\[',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response.text, re.IGNORECASE)
            patterns_found[pattern] = len(matches)
        
        return {
            "status": "success",
            "response_code": response.status_code,
            "html_length": len(response.text),
            "patterns_found": patterns_found,
            "html_preview": response.text[:1000]
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)