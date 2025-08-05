import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from forexconnect import ForexConnect
import datetime
import json
import requests
from typing import Optional, List, Dict, Any
import cloudscraper
import re
import time
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import random

app = FastAPI(title="Forex Data & Calendar API", description="Forex data multi-timeframe + economic calendar")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Alternative ForexRequest model for API-based data retrieval
class AlternativeForexRequest(BaseModel):
    symbol: str
    timeframe: str
    count: int

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
        "endpoints": ["/get-forex-data", "/get-alternative-forex-data", "/get-economic-calendar", "/debug-calendar", "/test-scraper"]
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

@app.post("/get-alternative-forex-data")
async def get_alternative_forex_data(request: AlternativeForexRequest):
    """Get historical forex data from alternative source"""
    try:
        # This is a placeholder for the actual forex data retrieval
        # In a real implementation, you would connect to a forex data provider
        return {
            "status": "success",
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "count": request.count,
            "data": [
                # Sample data structure
                {
                    "timestamp": int(time.time()) - 3600 * i,
                    "open": 1.1 + (i * 0.001),
                    "high": 1.11 + (i * 0.001),
                    "low": 1.09 + (i * 0.001),
                    "close": 1.105 + (i * 0.001),
                    "volume": 1000 + (i * 10)
                } for i in range(request.count)
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================
# Economic Calendar Models
# ==========================
class CalendarEvent(BaseModel):
    date: str
    time: str
    currency: str
    impact: str
    event: str
    forecast: Optional[str] = ""
    actual: Optional[str] = ""
    previous: Optional[str] = ""

class CalendarResponse(BaseModel):
    status: str
    events: List[CalendarEvent]
    total_events: int
    source: str
    filters: Dict[str, Any]

# ==========================
# API-Based Calendar Functions
# ==========================
# Function to fetch economic calendar data from Investing.com API
def fetch_investing_calendar(currencies=None, impact="High"):
    """Fetch economic calendar data from Investing.com API"""
    try:
        # Convert currencies to list if provided
        currency_list = currencies.split(',') if currencies else None
        
        # Map impact levels to Investing.com importance values
        impact_map = {
            "High": 3,
            "Medium": 2,
            "Low": 1,
            "All": None
        }
        
        # Set up date range (current week)
        today = datetime.now()
        start_date = today.strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        
        # Set up API request parameters
        params = {
            "timeframe": 86400,  # Daily timeframe
            "timeZone": 8,       # GMT timezone
            "dateFrom": start_date,
            "dateTo": end_date,
            "currentTab": "custom",
            "limit": 50,
            "importanceMin": impact_map.get(impact, 1),
            "viewType": "calendar"
        }
        
        # Add currency filter if provided
        if currency_list:
            # Map common currency codes to country IDs used by Investing.com
            currency_map = {
                "USD": 5,   # United States
                "EUR": 72,  # Euro Zone
                "GBP": 4,   # United Kingdom
                "JPY": 35,  # Japan
                "AUD": 25,  # Australia
                "CAD": 6,   # Canada
                "CHF": 12,  # Switzerland
                "NZD": 43,  # New Zealand
                "CNY": 37   # China
            }
            
            country_ids = [str(currency_map.get(curr, 0)) for curr in currency_list if curr in currency_map]
            if country_ids:
                params["countries"] = ",".join(country_ids)
        
        # Set up headers to mimic browser request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.investing.com/economic-calendar/",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        # Make API request
        url = "https://api.investing.com/api/calendar/events"
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        # Check response status
        if response.status_code != 200:
            print(f"API request failed with status code: {response.status_code}")
            return fetch_alternative_calendar(currencies, impact)
        
        # Parse response JSON
        data = response.json()
        
        # Extract events
        events = []
        for item in data.get("data", []):
            # Map importance level
            importance = item.get("importance", 0)
            impact_level = "Low"
            if importance == 3:
                impact_level = "High"
            elif importance == 2:
                impact_level = "Medium"
            
            # Extract currency code
            country = item.get("country", "")
            currency_code = country.get("code", "") if isinstance(country, dict) else ""
            
            # Create event object
            event = {
                "date": item.get("date", "").split("T")[0] if "T" in item.get("date", "") else item.get("date", ""),
                "time": item.get("time", ""),
                "currency": currency_code,
                "impact": impact_level,
                "event": item.get("name", ""),
                "forecast": item.get("forecast", ""),
                "actual": item.get("actual", ""),
                "previous": item.get("previous", "")
            }
            
            events.append(event)
        
        return {
            "status": "success",
            "events": events,
            "total_events": len(events),
            "source": "investing.com",
            "filters": {
                "currencies": currency_list,
                "impact": impact
            }
        }
    
    except Exception as e:
        print(f"Error fetching from Investing.com API: {e}")
        return fetch_alternative_calendar(currencies, impact)

# Function to fetch calendar data from alternative API
def fetch_alternative_calendar(currencies=None, impact="High"):
    """Fetch economic calendar data from alternative API"""
    try:
        # Convert currencies to list if provided
        currency_list = currencies.split(',') if currencies else None
        
        # Try MarketAux API (requires API key - using free tier)
        api_key = "YOUR_API_KEY"  # Replace with your API key
        
        # Set up date range (current week)
        today = datetime.now()
        start_date = today.strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        
        # Set up API request parameters
        params = {
            "api_key": api_key,
            "from_date": start_date,
            "to_date": end_date,
            "countries": currencies if currencies else ""
        }
        
        # Make API request
        url = "https://api.marketaux.com/v1/calendar"
        response = requests.get(url, params=params, timeout=30)
        
        # Check response status
        if response.status_code != 200:
            print(f"MarketAux API request failed with status code: {response.status_code}")
            return fetch_mocked_calendar(currencies, impact)
        
        # Parse response JSON
        data = response.json()
        
        # Extract events
        events = []
        for item in data.get("data", []):
            # Map importance level
            importance = item.get("importance", "")
            impact_level = "Low"
            if importance == "high":
                impact_level = "High"
            elif importance == "medium":
                impact_level = "Medium"
            
            # Filter by impact
            if impact != "All" and impact_level != impact:
                continue
            
            # Create event object
            event = {
                "date": item.get("date", ""),
                "time": item.get("time", ""),
                "currency": item.get("country", ""),
                "impact": impact_level,
                "event": item.get("title", ""),
                "forecast": item.get("forecast", ""),
                "actual": item.get("actual", ""),
                "previous": item.get("previous", "")
            }
            
            events.append(event)
        
        return {
            "status": "success",
            "events": events,
            "total_events": len(events),
            "source": "marketaux.com",
            "filters": {
                "currencies": currency_list,
                "impact": impact
            }
        }
    
    except Exception as e:
        print(f"Error fetching from MarketAux API: {e}")
        return fetch_mocked_calendar(currencies, impact)

# Function to generate mocked calendar data as fallback
def fetch_mocked_calendar(currencies=None, impact="High"):
    """Generate mocked economic calendar data as fallback"""
    # Convert currencies to list if provided
    currency_list = currencies.split(',') if currencies else ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
    
    # If no specific currencies requested, use major ones
    if not currencies:
        currency_list = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
    
    # Generate dates for the next 7 days
    dates = []
    today = datetime.now()
    for i in range(7):
        date = today + timedelta(days=i)
        dates.append(date.strftime("%Y-%m-%d"))
    
    # Sample economic events
    event_templates = [
        {"name": "Interest Rate Decision", "impact": "High"},
        {"name": "Non-Farm Payrolls", "impact": "High"},
        {"name": "CPI m/m", "impact": "High"},
        {"name": "GDP q/q", "impact": "High"},
        {"name": "Retail Sales m/m", "impact": "Medium"},
        {"name": "Unemployment Rate", "impact": "Medium"},
        {"name": "Manufacturing PMI", "impact": "Medium"},
        {"name": "Trade Balance", "impact": "Low"},
        {"name": "Industrial Production m/m", "impact": "Low"},
        {"name": "Building Permits", "impact": "Low"}
    ]
    
    # Generate events
    events = []
    for date in dates:
        # Generate 2-4 events per day
        num_events = min(len(currency_list), 4)
        for i in range(num_events):
            # Select random currency and event
            currency = currency_list[i % len(currency_list)]
            event_template = event_templates[i % len(event_templates)]
            
            # Filter by impact
            if impact != "All" and event_template["impact"] != impact:
                continue
            
            # Generate random time
            hour = (8 + i * 2) % 24
            minute = 0 if hour % 2 == 0 else 30
            time_str = f"{hour:02d}:{minute:02d}"
            
            # Generate random values
            forecast = f"{(i * 0.1 + 0.5):.1f}%"
            previous = f"{(i * 0.1 + 0.3):.1f}%"
            
            # Create event
            event = {
                "date": date,
                "time": time_str,
                "currency": currency,
                "impact": event_template['impact'],
                "event": f"{currency} {event_template['name']}",
                "forecast": forecast,
                "actual": "",  # No actual value for future events
                "previous": previous
            }
            
            events.append(event)
    
    return {
        "status": "success",
        "events": events,
        "total_events": len(events),
        "source": "mocked_data",
        "filters": {
            "currencies": currency_list,
            "impact": impact
        }
    }

# ==========================
# Web Scraping Calendar Functions - IMPROVED VERSION
# ==========================
def clean_json_string(raw_json):
    """
    Membersihkan string JSON dari ForexFactory dengan metode yang lebih robust
    """
    try:
        # Hapus whitespace di awal dan akhir
        raw_json = raw_json.strip()
        
        # Hapus trailing semicolon jika ada
        if raw_json.endswith(";"):
            raw_json = raw_json[:-1]
        
        # Periksa apakah JSON dimulai dengan '{' - jika tidak, cari yang benar
        if not raw_json.startswith('{'):
            # Cari opening brace pertama
            brace_pos = raw_json.find('{')
            if brace_pos != -1:
                raw_json = raw_json[brace_pos:]
            else:
                raise Exception("No opening brace found in JSON string")
        
        # Hapus single line comments dengan lebih hati-hati
        lines = raw_json.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove // comments but preserve strings
            in_string = False
            escaped = False
            comment_pos = -1
            
            for i, char in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if char == '\\':
                    escaped = True
                    continue
                if char == '"' and not escaped:
                    in_string = not in_string
                elif not in_string and char == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    comment_pos = i
                    break
            
            if comment_pos >= 0:
                line = line[:comment_pos].rstrip()
            cleaned_lines.append(line)
        
        raw_json = '\n'.join(cleaned_lines)
        
        # Remove block comments /* */
        raw_json = re.sub(r'/\*.*?\*/', '', raw_json, flags=re.DOTALL)
        
        # Fix unquoted object keys - lebih spesifik
        # Match pattern: word character followed by colon
        raw_json = re.sub(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'"\1":', raw_json)
        
        # Fix numeric keys - only pure numbers
        raw_json = re.sub(r'(?<=[{,\s\n])(\d+)(\s*:)', r'"\1"\2', raw_json)
        
        # Fix undefined, null, true, false values
        raw_json = re.sub(r':\s*undefined\b', ': null', raw_json)
        raw_json = re.sub(r':\s*True\b', ': true', raw_json)
        raw_json = re.sub(r':\s*False\b', ': false', raw_json)
        
        # Fix single quotes to double quotes for strings
        # Pattern: single quote, content, single quote (be more specific)
        raw_json = re.sub(r"(?<=[:,\[\s])'([^'\\]*(?:\\.[^'\\]*)*)'(?=[,\]\}\s])", r'"\1"', raw_json)
        
        # Remove trailing commas
        raw_json = re.sub(r',(\s*[}\]])', r'\1', raw_json)
        
        # Fix any remaining issues with quotes
        # Remove extra quotes around already quoted strings
        raw_json = re.sub(r'""([^"]*?)""', r'"\1"', raw_json)
        
        # Final check: pastikan dimulai dan diakhiri dengan brace yang benar
        raw_json = raw_json.strip()
        if not raw_json.startswith('{'):
            raise Exception("Cleaned JSON does not start with opening brace")
        
        # Hitung brace untuk memastikan balanced
        open_braces = raw_json.count('{')
        close_braces = raw_json.count('}')
        if open_braces != close_braces:
            print(f"Warning: Unbalanced braces - open: {open_braces}, close: {close_braces}")
        
        return raw_json
        
    except Exception as e:
        raise Exception(f"Error cleaning JSON: {str(e)}")

def extract_calendar_json_multiple_methods(html):
    """
    Coba beberapa metode untuk ekstraksi data kalender dengan perbaikan
    """
    methods = [
        # Method 1: calendarComponentStates[1] - yang paling spesifik
        {
            'name': 'calendarComponentStates[1]',
            'pattern': r'window\.calendarComponentStates\[1\]\s*=\s*({.*?});',
            'flags': re.DOTALL
        },
        # Method 2: calendarComponentStates dengan index apapun
        {
            'name': 'calendarComponentStates_indexed',
            'pattern': r'window\.calendarComponentStates\[\d+\]\s*=\s*({.*?});',
            'flags': re.DOTALL
        },
        # Method 3: calendarComponentStates general
        {
            'name': 'calendarComponentStates_general',
            'pattern': r'calendarComponentStates.*?=\s*({.*?});',
            'flags': re.DOTALL
        }
    ]
    
    for method in methods:
        try:
            matches = re.findall(method['pattern'], html, method['flags'])
            if matches:
                print(f"Found data using method: {method['name']}")
                # Take the first match that looks like valid JSON
                for match in matches:
                    if match.strip().startswith('{') and 'days' in match:
                        return match, method['name']
        except Exception as e:
            print(f"Method {method['name']} failed: {e}")
            continue
    
    # Method 4: Manual extraction dengan perbaikan
    try:
        # Look for calendarComponentStates[1] specifically
        start_pattern = r'window\.calendarComponentStates\[1\]\s*=\s*'
        start_match = re.search(start_pattern, html)
        
        if start_match:
            start_pos = start_match.end()
            
            # Find the opening brace
            brace_start = html.find('{', start_pos)
            if brace_start != -1:
                # Use bracket counting to find the matching closing brace
                brace_count = 0
                pos = brace_start
                
                while pos < len(html):
                    char = html[pos]
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Check if this is followed by semicolon (end of statement)
                            next_pos = pos + 1
                            while next_pos < len(html) and html[next_pos] in ' \n\t':
                                next_pos += 1
                            
                            if next_pos < len(html) and html[next_pos] == ';':
                                raw_json = html[brace_start:pos + 1]
                                return raw_json, 'manual_bracket_matching_improved'
                    pos += 1
        
        # Fallback: try to find any calendarComponentStates
        start_pattern = r'window\.calendarComponentStates\s*\[\s*\d+\s*\]\s*=\s*'
        start_match = re.search(start_pattern, html)
        
        if start_match:
            start_pos = start_match.end()
            brace_start = html.find('{', start_pos)
            
            if brace_start != -1:
                brace_count = 0
                pos = brace_start
                
                while pos < len(html):
                    char = html[pos]
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            next_pos = pos + 1
                            while next_pos < len(html) and html[next_pos] in ' \n\t':
                                next_pos += 1
                            
                            if next_pos < len(html) and html[next_pos] == ';':
                                raw_json = html[brace_start:pos + 1]
                                return raw_json, 'manual_bracket_matching_fallback'
                    pos += 1
                    
    except Exception as e:
        print(f"Manual extraction failed: {e}")
    
    raise Exception("No calendar data found using any method")

def parse_html_table_fallback(html):
    """
    Fallback method: parse HTML table directly if JSON extraction fails
    """
    events = []
    
    # Look for calendar table rows
    table_pattern = r'<tr[^>]*class[^>]*calendar_row[^>]*>.*?</tr>'
    rows = re.findall(table_pattern, html, re.DOTALL)
    
    for row in rows:
        try:
            # Extract basic info from HTML
            date_match = re.search(r'data-date["\']?\s*=\s*["\']?([^"\'>\s]+)', row)
            time_match = re.search(r'class["\']?[^>]*time[^>]*>([^<]+)', row)
            currency_match = re.search(r'class["\']?[^>]*currency[^>]*>([^<]+)', row)
            impact_match = re.search(r'class["\']?[^>]*impact[^>]*', row)
            event_match = re.search(r'class["\']?[^>]*event[^>]*>([^<]+)', row)
            
            if date_match and time_match and currency_match and event_match:
                # Determine impact level from class names
                impact_level = "Unknown"
                if 'holiday' in row:
                    impact_level = "Holiday"
                elif 'high' in row.lower():
                    impact_level = "High"
                elif 'medium' in row.lower():
                    impact_level = "Medium"
                elif 'low' in row.lower():
                    impact_level = "Low"
                
                events.append({
                    "date": date_match.group(1).strip(),
                    "time": time_match.group(1).strip(),
                    "currency": currency_match.group(1).strip(),
                    "impact": impact_level,
                    "event": event_match.group(1).strip(),
                    "forecast": "",
                    "actual": "",
                    "previous": ""
                })
        except Exception as e:
            print(f"Error parsing HTML row: {e}")
            continue
    
    return events

@app.get("/get-economic-calendar")
async def get_economic_calendar(currencies: Optional[str] = None, impact: str = "High"):
    try:
        # First try to get data from Investing.com API (primary source)
        api_data = fetch_investing_calendar(currencies, impact)
        
        # If API data is successful and has events, return it
        if api_data.get("status") == "success" and len(api_data.get("events", [])) > 0:
            return api_data
        
        # If API approach failed or returned no events, try web scraping as fallback
        # Convert currencies string to list if provided
        currency_list = currencies.split(',') if currencies else None
        
        # Create scraper with better headers
        scraper = cloudscraper.create_scraper(
            delay=10,
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0"
        }
        
        print("Fetching ForexFactory calendar...")
        response = scraper.get(url, headers=headers, timeout=30)
        html = response.text
        
        print(f"HTML length: {len(html)}")
        print(f"Response status: {response.status_code}")
        
        events = []
        
        try:
            # Try to extract JSON data
            raw_json, method = extract_calendar_json_multiple_methods(html)
            print(f"Extracted JSON using method: {method}")
            print(f"Raw JSON length: {len(raw_json)}")
            
            # Clean the JSON string
            cleaned_json = clean_json_string(raw_json)
            print(f"Cleaned JSON length: {len(cleaned_json)}")
            
            # Parse JSON
            try:
                data = json.loads(cleaned_json)
                print(f"Successfully parsed JSON data")
                print(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                
                # Find calendar data - try different possible keys
                calendar_data = None
                possible_keys = ["1", "0", "today", "calendar", "componentStates"]
                
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
                        # Try to find any object with 'days' property
                        for key, value in data.items():
                            if isinstance(value, dict) and "days" in value:
                                calendar_data = value
                                print(f"Found calendar data in nested key: {key}")
                                break
                
                if calendar_data:
                    # Extract events from JSON
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
                            
                            # Debug: print event info
                            print(f"Event: {ev.get('name', 'Unknown')}, Impact: '{event_impact}', Currency: '{event_currency}'")
                            
                            # Filter by impact - more flexible matching
                            impact_match = False
                            if impact.lower() == "all":
                                impact_match = True
                            elif impact.lower() in event_impact:
                                impact_match = True
                            elif impact.lower() == "high" and any(word in event_impact for word in ["high", "red"]):
                                impact_match = True
                            elif impact.lower() == "medium" and any(word in event_impact for word in ["medium", "orange", "yellow"]):
                                impact_match = True
                            elif impact.lower() == "low" and any(word in event_impact for word in ["low", "green"]):
                                impact_match = True
                            
                            if not impact_match:
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
                    
                    print(f"Found {len(events)} matching events from JSON")
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                print(f"Error at position: {e.pos}")
                if e.pos < len(cleaned_json):
                    context = cleaned_json[max(0, e.pos-100):e.pos+100]
                    print(f"Context around error: {context}")
                # Fall back to HTML parsing
                events = []
        
        except Exception as json_error:
            print(f"JSON extraction failed: {json_error}")
            events = []
        
        # If no events found yet, try HTML table parsing as fallback
        if not events:
            print("Falling back to HTML table parsing...")
            try:
                events = parse_html_table_fallback(html)
                print(f"Found {len(events)} events from HTML parsing")
            except Exception as html_error:
                print(f"HTML parsing also failed: {html_error}")
        
        # Apply filters to all events
        if events and (currency_list or impact != "all"):
            print(f"Applying filters - currencies: {currency_list}, impact: {impact}")
            filtered_events = []
            for event in events:
                event_impact = event.get("impact", "").lower()
                event_currency = event.get("currency", "")
                
                # Filter by impact
                impact_match = False
                if impact.lower() == "all":
                    impact_match = True
                elif impact.lower() in event_impact:
                    impact_match = True
                elif impact.lower() == "high" and any(word in event_impact for word in ["high", "red"]):
                    impact_match = True
                elif impact.lower() == "medium" and any(word in event_impact for word in ["medium", "orange", "yellow"]):
                    impact_match = True
                elif impact.lower() == "low" and any(word in event_impact for word in ["low", "green", "yel"]):
                    impact_match = True
                elif impact.lower() == "non-economic" and any(word in event_impact for word in ["non-economic", "holiday", "gra"]):
                    impact_match = True
                
                if not impact_match:
                    print(f"Event filtered out by impact: {event.get('event', 'Unknown')} - {event_impact}")
                    continue
                
                # Filter by currency if specified
                if currency_list and event_currency not in currency_list:
                    print(f"Event filtered out by currency: {event.get('event', 'Unknown')} - {event_currency}")
                    continue
                
                filtered_events.append(event)
            
            events = filtered_events
            print(f"After filtering: {len(events)} events")
        
        # If web scraping found events, return them
        if events:
            return {
                "status": "success", 
                "events": events,
                "total_events": len(events),
                "source": "forexfactory.com",
                "filters": {
                    "currencies": currency_list,
                    "impact": impact
                }
            }
        
        # If web scraping failed but we have API data (even if empty), return it
        if api_data.get("status") == "success":
            return api_data
        
        # If still no events, provide debug info
        print("No events found after all attempts")
        # Return debug info
        return {
            "status": "success", 
            "events": [],
            "total_events": 0,
            "debug_info": {
                "html_length": len(html),
                "raw_json_found": 'raw_json' in locals(),
                "raw_json_length": len(raw_json) if 'raw_json' in locals() else 0,
                "extraction_method": method if 'method' in locals() else "none",
                "data_event_rows": len(re.findall(r'data-event-id=', html)),
                "filters_applied": {
                    "currencies": currency_list,
                    "impact": impact
                }
            },
            "filters": {
                "currencies": currency_list,
                "impact": impact
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        # Try to return API data if available, even in case of error with web scraping
        try:
            api_data = fetch_investing_calendar(currencies, impact)
            if api_data.get("status") == "success":
                return api_data
        except:
            pass
            
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic calendar: {str(e)}")

@app.get("/debug-calendar")
async def debug_calendar(currencies: Optional[str] = None, impact: Optional[str] = "High"):
    """
    Endpoint for comprehensive debugging of economic calendar data from all sources
    """
    try:
        # Initialize debug info dictionary
        debug_info = {
            "api_sources": {},
            "web_scraping": {}
        }
        
        # 1. Try Investing.com API
        try:
            investing_data = fetch_investing_calendar(currencies, impact)
            debug_info["api_sources"]["investing.com"] = {
                "status": investing_data.get("status"),
                "events_count": len(investing_data.get("events", [])),
                "sample_event": investing_data.get("events", [])[0] if investing_data.get("events", []) else None,
                "source": investing_data.get("source"),
                "filters_applied": investing_data.get("filters")
            }
        except Exception as e:
            debug_info["api_sources"]["investing.com"] = {
                "status": "error",
                "error": str(e)
            }
        
        # 2. Try MarketAux API (alternative source)
        try:
            marketaux_data = fetch_alternative_calendar(currencies, impact)
            debug_info["api_sources"]["marketaux.com"] = {
                "status": marketaux_data.get("status"),
                "events_count": len(marketaux_data.get("events", [])),
                "sample_event": marketaux_data.get("events", [])[0] if marketaux_data.get("events", []) else None,
                "source": marketaux_data.get("source"),
                "filters_applied": marketaux_data.get("filters")
            }
        except Exception as e:
            debug_info["api_sources"]["marketaux.com"] = {
                "status": "error",
                "error": str(e)
            }
        
        # 3. Try mocked data
        try:
            mocked_data = fetch_mocked_calendar(currencies, impact)
            debug_info["api_sources"]["mocked_data"] = {
                "status": mocked_data.get("status"),
                "events_count": len(mocked_data.get("events", [])),
                "sample_event": mocked_data.get("events", [])[0] if mocked_data.get("events", []) else None,
                "source": mocked_data.get("source"),
                "filters_applied": mocked_data.get("filters")
            }
        except Exception as e:
            debug_info["api_sources"]["mocked_data"] = {
                "status": "error",
                "error": str(e)
            }
        
        # 4. Try ForexFactory web scraping
        try:
            scraper = cloudscraper.create_scraper(delay=10)
            url = "https://www.forexfactory.com/calendar"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = scraper.get(url, headers=headers, timeout=30)
            html = response.text
            
            debug_info["web_scraping"]["forexfactory.com"] = {
                "html_length": len(html),
                "response_status": response.status_code,
                "extraction_attempts": []
            }
            
            # Try each extraction method
            try:
                raw_json, method = extract_calendar_json_multiple_methods(html)
                
                attempt_info = {
                    "method": method,
                    "raw_json_length": len(raw_json),
                    "raw_preview": raw_json[:500],  # Increased preview length
                    "status": "extracted"
                }
                
                try:
                    cleaned_json = clean_json_string(raw_json)
                    attempt_info["cleaned_json_length"] = len(cleaned_json)
                    attempt_info["cleaned_preview"] = cleaned_json[:500]  # Increased preview length
                    
                    try:
                        parsed_data = json.loads(cleaned_json)
                        attempt_info["status"] = "success"
                        attempt_info["data_keys"] = list(parsed_data.keys()) if isinstance(parsed_data, dict) else "Not a dict"
                        attempt_info["data_type"] = str(type(parsed_data))
                        
                        # Detailed structure analysis
                        structure_info = {}
                        if isinstance(parsed_data, dict):
                            for key, value in parsed_data.items():
                                structure_info[key] = {
                                    "type": str(type(value)),
                                    "length": len(value) if isinstance(value, (list, dict, str)) else "N/A"
                                }
                                
                                # Check if this looks like calendar data
                                if isinstance(value, dict):
                                    sub_keys = list(value.keys())[:10]  # First 10 keys
                                    structure_info[key]["sub_keys"] = sub_keys
                                    
                                    # Check for calendar-like structure
                                    if 'days' in value:
                                        days = value.get('days', [])
                                        structure_info[key]["days_count"] = len(days)
                                        
                                        # Sample first day structure
                                        if days and isinstance(days, list) and len(days) > 0:
                                            first_day = days[0]
                                            if isinstance(first_day, dict):
                                                structure_info[key]["first_day_keys"] = list(first_day.keys())
                                                if 'events' in first_day:
                                                    events = first_day.get('events', [])
                                                    structure_info[key]["first_day_events_count"] = len(events)
                                                    
                                                    # Sample first event structure
                                                    if events and len(events) > 0:
                                                        first_event = events[0]
                                                        if isinstance(first_event, dict):
                                                            structure_info[key]["first_event_keys"] = list(first_event.keys())
                                                            structure_info[key]["first_event_sample"] = {k: str(v)[:50] for k, v in first_event.items()}
                        
                        attempt_info["structure_info"] = structure_info
                        
                        # Look for ALL possible calendar structures
                        calendar_info = {}
                        def find_calendar_data(obj, path=""):
                            if isinstance(obj, dict):
                                for key, value in obj.items():
                                    current_path = f"{path}.{key}" if path else key
                                    if isinstance(value, dict) and 'days' in value:
                                        days = value.get('days', [])
                                        events_count = 0
                                        for day in days:
                                            if isinstance(day, dict) and 'events' in day:
                                                events_count += len(day.get('events', []))
                                        
                                        calendar_info[current_path] = {
                                            'days_count': len(days),
                                            'events_count': events_count,
                                            'sample_day_keys': list(days[0].keys()) if days and isinstance(days[0], dict) else []
                                        }
                                    elif isinstance(value, (dict, list)):
                                        find_calendar_data(value, current_path)
                            elif isinstance(obj, list):
                                for i, item in enumerate(obj[:5]):  # Check first 5 items
                                    find_calendar_data(item, f"{path}[{i}]")
                        
                        find_calendar_data(parsed_data)
                        attempt_info["all_calendar_structures"] = calendar_info
                        
                    except json.JSONDecodeError as e:
                        attempt_info["status"] = "json_error"
                        attempt_info["json_error"] = str(e)
                        attempt_info["error_pos"] = e.pos
                        if e.pos < len(cleaned_json):
                            attempt_info["error_context"] = cleaned_json[max(0, e.pos-100):e.pos+100]
                    
                except Exception as clean_error:
                    attempt_info["status"] = "cleaning_error"
                    attempt_info["cleaning_error"] = str(clean_error)
                
                debug_info["web_scraping"]["forexfactory.com"]["extraction_attempts"].append(attempt_info)
                
            except Exception as extraction_error:
                debug_info["web_scraping"]["forexfactory.com"]["extraction_attempts"].append({
                    "method": "all_methods",
                    "status": "extraction_error",
                    "error": str(extraction_error)
                })
            
            # Enhanced HTML table analysis
            table_patterns = [
                r'<tr[^>]*class[^>]*calendar_row[^>]*>',
                r'<tr[^>]*calendar[^>]*>',
                r'<div[^>]*class[^>]*event[^>]*>',
                r'data-event[^>]*>',
                r'class[^>]*currency[^>]*>'
            ]
            
            table_analysis = {}
            for pattern in table_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                table_analysis[pattern] = {
                    "count": len(matches),
                    "samples": matches[:3] if matches else []
                }
            
            debug_info["web_scraping"]["forexfactory.com"]["html_table_analysis"] = table_analysis
            
            # Look for any JavaScript variables that might contain calendar data
            js_var_patterns = [
                r'var\s+(\w+)\s*=\s*\{[^}]*calendar[^}]*\}',
                r'window\.(\w+)\s*=\s*\{[^}]*calendar[^}]*\}',
                r'(\w+)\s*=\s*\{[^}]*days[^}]*\}',
                r'(\w+)\s*=\s*\{[^}]*events[^}]*\}'
            ]
            
            js_variables = {}
            for pattern in js_var_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    js_variables[pattern] = matches[:5]  # First 5 matches
            
            debug_info["web_scraping"]["forexfactory.com"]["js_variables_found"] = js_variables
            
            # Try parsing the HTML table as a fallback
            events = parse_html_table_fallback(html, currencies, impact)
            debug_info["web_scraping"]["forexfactory.com"]["html_table_parsing"] = {
                "events_found": len(events) > 0,
                "events_count": len(events),
                "sample_event": events[0] if events else None
            }
            
        except Exception as e:
            if "web_scraping" not in debug_info:
                debug_info["web_scraping"] = {}
            debug_info["web_scraping"]["forexfactory.com"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Add summary of all sources
        debug_info["summary"] = {
            "api_sources_available": len(debug_info["api_sources"]),
            "api_sources_successful": sum(1 for source in debug_info["api_sources"].values() if source.get("status") == "success"),
            "web_scraping_successful": "forexfactory.com" in debug_info["web_scraping"] and debug_info["web_scraping"]["forexfactory.com"].get("response_status") == 200,
            "total_events_found": sum(source.get("events_count", 0) for source in debug_info["api_sources"].values()) + 
                                  debug_info["web_scraping"].get("forexfactory.com", {}).get("html_table_parsing", {}).get("events_count", 0),
            "filters_applied": {
                "currencies": currencies,
                "impact": impact
            }
        }
        
        return {"status": "success", "debug_info": debug_info}
        
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

@app.get("/raw-calendar-data")
async def get_raw_calendar_data():
    """
    Endpoint untuk melihat raw data yang diekstrak dari ForexFactory
    """
    try:
        scraper = cloudscraper.create_scraper(delay=10)
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = scraper.get(url, headers=headers, timeout=30)
        html = response.text
        
        try:
            raw_json, method = extract_calendar_json_multiple_methods(html)
            cleaned_json = clean_json_string(raw_json)
            parsed_data = json.loads(cleaned_json)
            
            return {
                "status": "success",
                "extraction_method": method,
                "raw_json_preview": raw_json[:1000],
                "cleaned_json_preview": cleaned_json[:1000],
                "parsed_data": parsed_data,
                "data_summary": {
                    "type": str(type(parsed_data)),
                    "keys": list(parsed_data.keys()) if isinstance(parsed_data, dict) else "Not a dict",
                    "length": len(parsed_data) if isinstance(parsed_data, (list, dict)) else "N/A"
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "html_length": len(html),
                "html_preview": html[:1000]
            }
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/inspect-html")
async def inspect_html():
    """
    Endpoint untuk melihat HTML yang diterima dari ForexFactory
    """
    try:
        scraper = cloudscraper.create_scraper(delay=10)
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        response = scraper.get(url, headers=headers, timeout=30)
        html = response.text
        
        # Check for various indicators
        indicators = {
            "html_length": len(html),
            "response_status": response.status_code,
            "contains_calendar": "calendar" in html.lower(),
            "contains_events": "event" in html.lower(),
            "contains_cloudflare": "cloudflare" in html.lower(),
            "contains_checking_browser": "checking your browser" in html.lower(),
            "contains_javascript_disabled": "javascript" in html.lower(),
            "data_event_count": len(re.findall(r'data-event-id=', html)),
            "calendar_component_states": "calendarComponentStates" in html,
            "table_rows": len(re.findall(r'<tr', html, re.IGNORECASE)),
            "script_tags": len(re.findall(r'<script', html, re.IGNORECASE))
        }
        
        # Get sample of HTML content
        html_sample = {
            "first_1000": html[:1000],
            "contains_head": "<head>" in html,
            "contains_body": "<body>" in html,
            "title": re.search(r'<title>(.*?)</title>', html, re.IGNORECASE).group(1) if re.search(r'<title>(.*?)</title>', html, re.IGNORECASE) else "No title found"
        }
        
        return {
            "status": "success",
            "indicators": indicators,
            "html_sample": html_sample,
            "response_headers": dict(response.headers)
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)