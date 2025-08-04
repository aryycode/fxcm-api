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
# Forex Factory Scraper - IMPROVED VERSION
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
        
        return raw_json
        
    except Exception as e:
        raise Exception(f"Error cleaning JSON: {str(e)}")

def extract_calendar_json_multiple_methods(html):
    """
    Coba beberapa metode untuk ekstraksi data kalender
    """
    methods = [
        # Method 1: calendarComponentStates
        {
            'name': 'calendarComponentStates',
            'pattern': r'window\.calendarComponentStates\s*=\s*({.*?});',
            'flags': re.DOTALL
        },
        # Method 2: cakgalVars
        {
            'name': 'cakgalVars',
            'pattern': r'var\s+cakgalVars\s*=\s*({.*?});',
            'flags': re.DOTALL
        },
        # Method 3: calendar data in script tags
        {
            'name': 'script_calendar',
            'pattern': r'(?:calendar|events).*?=\s*({.*?});',
            'flags': re.DOTALL | re.IGNORECASE
        }
    ]
    
    for method in methods:
        try:
            matches = re.findall(method['pattern'], html, method['flags'])
            if matches:
                print(f"Found data using method: {method['name']}")
                return matches[0], method['name']
        except Exception as e:
            print(f"Method {method['name']} failed: {e}")
            continue
    
    # Method 4: Manual bracket matching for calendarComponentStates
    try:
        start_pattern = r'window\.calendarComponentStates\s*='
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
                            raw_json = html[brace_start:pos + 1]
                            return raw_json, 'manual_bracket_matching'
                    pos += 1
    except Exception as e:
        print(f"Manual bracket matching failed: {e}")
    
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
        
        # If JSON parsing failed, try HTML table parsing as fallback
        if not events:
            print("Falling back to HTML table parsing...")
            try:
                events = parse_html_table_fallback(html)
                print(f"Found {len(events)} events from HTML parsing")
                
                # Apply filters to HTML-parsed events
                if currency_list or impact != "High":
                    filtered_events = []
                    for event in events:
                        event_impact = event.get("impact", "").lower()
                        event_currency = event.get("currency", "")
                        
                        # Filter by impact
                        if impact.lower() not in event_impact and impact.lower() != "all":
                            continue
                        
                        # Filter by currency if specified
                        if currency_list and event_currency not in currency_list:
                            continue
                        
                        filtered_events.append(event)
                    
                    events = filtered_events
                    print(f"After filtering: {len(events)} events")
            
            except Exception as html_error:
                print(f"HTML parsing also failed: {html_error}")
                raise HTTPException(status_code=500, detail=f"Both JSON and HTML parsing failed. JSON error: {json_error}, HTML error: {html_error}")
        
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
    Endpoint untuk debugging ekstraksi data kalender dengan detail lebih lengkap
    """
    try:
        scraper = cloudscraper.create_scraper(delay=10)
        url = "https://www.forexfactory.com/calendar"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = scraper.get(url, headers=headers, timeout=30)
        html = response.text
        
        debug_info = {
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
            
            debug_info["extraction_attempts"].append(attempt_info)
            
        except Exception as extraction_error:
            debug_info["extraction_attempts"].append({
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
        
        debug_info["html_table_analysis"] = table_analysis
        
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
        
        debug_info["js_variables_found"] = js_variables
        
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

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9898)