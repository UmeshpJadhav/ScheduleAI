from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, date, timedelta, time
import os
import pytz
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from dateutil.parser import parse as parse_datetime
import dateparser
from dateparser.search import search_dates
from dotenv import load_dotenv
import re


load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
   "https://www.googleapis.com/auth/calendar"
]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
OAUTH_PORT = 8080  

def get_calendar_service(force_oauth: bool = False, force_freebusy: bool = False):
    """Get authenticated Google Calendar service"""
    try:
        creds = None
        
     
        if force_oauth or force_freebusy:
            print("Forcing OAuth flow...")
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            force_oauth = True
            
         
            if force_freebusy:
                print("Removing token to get fresh permissions...")
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
        
      
        if os.path.exists(TOKEN_FILE):
            print("Loading token from file...")
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                if not creds.valid:
                    if creds.expired and creds.refresh_token:
                        print("Refreshing expired token...")
                        creds.refresh(Request())
                        with open(TOKEN_FILE, "w") as token:
                            token.write(creds.to_json())
                    else:
                        print("Token invalid and no refresh token available")
                        creds = None
                        force_oauth = True
                else:
                    print("Token is valid")
            except Exception as e:
                print(f"Error loading token: {e}")
                creds = None
                force_oauth = True
        
       
        if not creds or force_oauth:
            print("Starting OAuth flow...")
            if not os.path.exists(CREDENTIALS_FILE):
                raise ValueError("credentials.json not found. Please download it from Google Cloud Console.")
            
    
            with open(CREDENTIALS_FILE) as f:
                creds_data = json.load(f)
            
            
            creds_data['installed']['redirect_uris'] = [f'http://localhost:{OAUTH_PORT}/callback']
            
         
            temp_creds_file = 'temp_credentials.json'
            with open(temp_creds_file, 'w') as f:
                json.dump(creds_data, f)
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    temp_creds_file,
                    SCOPES,
                    redirect_uri=f'http://localhost:{OAUTH_PORT}/callback'
                )
                
                
                for port in range(OAUTH_PORT, OAUTH_PORT + 5):
                    try:
                        print(f"Trying OAuth on port {port}...")
                        creds = flow.run_local_server(
                            port=port,
                            authorization_prompt_message="Please visit this URL: {url}",
                            success_message="The auth flow is complete; you may close this window.",
                            open_browser=True
                        )
                        break
                    except Exception as e:
                        print(f"Failed to start OAuth on port {port}: {e}")
                        continue
                
                if not creds:
                    raise ValueError("Failed to complete OAuth flow on all ports")
                    
                with open(TOKEN_FILE, "w") as token:
                    token.write(creds.to_json())
                
            finally:
              
                if os.path.exists(temp_creds_file):
                    os.remove(temp_creds_file)
            
        service = build("calendar", "v3", credentials=creds)
        print("Successfully created Calendar service")
        return service
        
    except Exception as e:
        print(f"Error in get_calendar_service: {e}")
        raise

def extract_date_time(message: str) -> Tuple[Optional[datetime], Optional[time]]:
    try:
        print(f"Extracting date/time from: {message}")
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        
       
        relative_phrases = {
            'today': now,
            'tomorrow': now + timedelta(days=1),
            'day after tomorrow': now + timedelta(days=2),
            'next week': now + timedelta(weeks=1),
            'next month': (now.replace(day=1) + timedelta(days=32)).replace(day=1),
            'next year': now.replace(year=now.year + 1, month=1, day=1)
        }
        
        
        for phrase, dt in relative_phrases.items():
            if phrase in message.lower():
                print(f"Matched relative date phrase: {phrase}")
      
                time_part = message.lower().replace(phrase, '').strip()
                time_obj = parse_time(time_part)
                return dt, time_obj
        
       
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for i, day in enumerate(days):
            if day in message.lower():
                days_ahead = (i - now.weekday()) % 7
                if days_ahead == 0:  
                    dt = now
                elif days_ahead == 1:  
                    dt = now + timedelta(days=1)
                else:  
                    dt = now + timedelta(days=days_ahead)
                print(f"Matched day of week: {day}, date: {dt}")
              
                time_part = message.lower().replace(day, '').strip()
                time_obj = parse_time(time_part)
                return dt, time_obj
        
        
        try:
            parsed_date = search_dates(
                message,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "TIMEZONE": "Asia/Kolkata",
                    "DATE_ORDER": "DMY",
                    "PREFER_DAY_OF_MONTH": "first"
                }
            )
            
            if parsed_date:
                date_str, parsed_dt = parsed_date[0]
                if isinstance(parsed_dt, datetime):
                 
                    if not parsed_dt.tzinfo:
                        parsed_dt = tz.localize(parsed_dt)
             
                    time_obj = parse_time(message)
                    if time_obj:
                        parsed_dt = parsed_dt.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
                    return parsed_dt, time_obj
        except Exception as e:
            print(f"Dateparser error: {e}")
        
        date_obj = None
        
       
        processed_message = re.sub(r'(\d{1,2})([a-zA-Z])', r'\1 \2', message)
        

        date_patterns = [
           
            (r'\b(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?[\s-]*(?:of[\s-]*)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:[\s-]*(\d{2,4}))?\b', 
             '%d %B %Y', 'day month year'),
            
            (r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[\s-]*(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?(?:[\s-]*(\d{2,4}))?\b',
             '%B %d %Y', 'month day year'),
            
            (r'\b(0?[1-9]|[12][0-9]|3[01])[\s-/](0?[1-9]|1[0-2])[\s-/](\d{2,4})\b',
             '%d-%m-%Y', 'day-month-year')
        ]
        
        for pattern, date_format, desc in date_patterns:
            try:
                for msg in [processed_message, message]:
                    match = re.search(pattern, msg, re.IGNORECASE)
                    if match:
                        date_str = match.group(0)
                        try:
                            
                            if 'month day' in desc:
                                
                                month_part = match.group(1).lower()
                                day_part = match.group(2)
                                year_part = match.group(3) if len(match.groups()) > 2 and match.group(3) else now.year
                                date_str = f"{month_part} {day_part} {year_part}"
                                date_format = '%B %d %Y'
                            elif 'day month' in desc:
                           
                                day_part = match.group(1)
                                month_part = match.group(2).lower()
                                year_part = match.group(3) if len(match.groups()) > 2 and match.group(3) else now.year
                                date_str = f"{day_part} {month_part} {year_part}"
                                date_format = '%d %B %Y'
                            
                            date_obj = datetime.strptime(date_str, date_format)
                            if date_obj:
                              
                                if date_obj < now and 'year' not in date_str:
                                    date_obj = date_obj.replace(year=now.year + 1)
                                date_obj = tz.localize(date_obj)
                                print(f"Extracted date ({desc}): {date_obj}")
                                break
                        except Exception as e:
                            print(f"Date parsing error with pattern '{desc}': {e}")
                            continue
                    if date_obj:
                        break
            except Exception as e:
                print(f"Error processing date pattern '{desc}': {e}")
                continue
        
       
        time_obj = parse_time(message)
        
     
        if date_obj and time_obj:
            combined = date_obj.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
            if not combined.tzinfo:
                combined = tz.localize(combined)
            return combined, time_obj
        
     
        if date_obj:
            if not date_obj.tzinfo:
                date_obj = tz.localize(date_obj)
            return date_obj, None
            
        if time_obj:
            return None, time_obj
            
        return None, None
        
    except Exception as e:
        print(f"Error extracting date/time: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def parse_time(message: str) -> Optional[time]:
    """Helper function to parse time from a string"""
    time_patterns = [
        (r'\b(0?[1-9]|1[0-2]):([0-5][0-9])\s*([ap]m)\b', '%I:%M %p'),  # 3:30 pm
        (r'\b(0?[1-9]|1[0-2])\s*([ap]m)\b', '%I %p'),  # 3 pm
        (r'\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b', '%H:%M'),  # 15:30
        (r'\b(1[0-2]|0?[1-9])([ap]m)\b', '%I%p'),  # 3pm
        (r'\b([01]?[0-9]|2[0-3])\b', '%H')  # 3 or 15
    ]
    
    for pattern, time_format in time_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            time_str = match.group(0)
            try:
                time_obj = datetime.strptime(time_str, time_format).time()
                print(f"Extracted time: {time_obj}")
                return time_obj
            except ValueError:
                continue
    return None

def suggest_available_slots(
    date: date,
    duration_minutes: int = 30,
    start_hour: int = 9,
    end_hour: int = 18,
) -> List[Tuple[datetime, datetime]]:
    """Suggest available slots using Google Calendar API"""
    try:
        print(f"Checking availability for date: {date}")
        
       
        service = get_calendar_service()
        if not service:
            return []
            
       
        tz = 'Asia/Kolkata'
        tz_info = pytz.timezone(tz)
        
       
        start_time = datetime.combine(date, time(start_hour, 0))
        end_time = datetime.combine(date, time(end_hour, 0))
        
      
        time_min = start_time.astimezone(tz_info).isoformat()
        time_max = end_time.astimezone(tz_info).isoformat()
        
        print(f"Querying availability from {time_min} to {time_max}")
        
        try:
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "timeZone": tz,
                "items": [{"id": "primary"}],
            }
            
            events_result = service.freebusy().query(body=body).execute()
            busy_times = events_result["calendars"]["primary"]["busy"]
            print(f"Found {len(busy_times)} busy time slots")
            
            slots = []
            current = start_time
            
            while current + timedelta(minutes=duration_minutes) <= end_time:
                slot_end = current + timedelta(minutes=duration_minutes)
                
               
                current_tz = current.astimezone(tz_info)
                slot_end_tz = slot_end.astimezone(tz_info)
                
               
                is_available = True
                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy["start"]).astimezone(tz_info)
                    busy_end = datetime.fromisoformat(busy["end"]).astimezone(tz_info)
                    
                    if current_tz < busy_end and slot_end_tz > busy_start:
                        is_available = False
                        break
                
                if is_available:
                    slots.append((current_tz, slot_end_tz))
                
                current += timedelta(minutes=30)
            
            print(f"Found {len(slots)} available slots")
            return slots
            
        except Exception as e:
       
            if "insufficientPermissions" in str(e):
                print("Insufficient permissions, forcing OAuth refresh...")
                service = get_calendar_service(force_freebusy=True)
                if not service:
                    return []
                
              
                events_result = service.freebusy().query(body=body).execute()
                busy_times = events_result["calendars"]["primary"]["busy"]
                print(f"Found {len(busy_times)} busy time slots after OAuth refresh")
                
                slots = []
                current = start_time
                
                while current + timedelta(minutes=duration_minutes) <= end_time:
                    slot_end = current + timedelta(minutes=duration_minutes)
                    
                   
                    current_tz = current.astimezone(tz_info)
                    slot_end_tz = slot_end.astimezone(tz_info)
                    
                  
                    is_available = True
                    for busy in busy_times:
                        busy_start = datetime.fromisoformat(busy["start"]).astimezone(tz_info)
                        busy_end = datetime.fromisoformat(busy["end"]).astimezone(tz_info)
                        
                        if current_tz < busy_end and slot_end_tz > busy_start:
                            is_available = False
                            break
                    
                    if is_available:
                        slots.append((current_tz, slot_end_tz))
                    
                    current += timedelta(minutes=30)
                
                print(f"Found {len(slots)} available slots after OAuth refresh")
                return slots
            
            raise
            
    except Exception as e:
        print(f"Error checking availability: {e}")
        return []

def is_time_slot_available(date: datetime, start_time: datetime, end_time: datetime) -> bool:
    """
    Check if a specific time slot is available in the calendar.
    
    Args:
        date: The date to check
        start_time: Start time of the slot
        end_time: End time of the slot
        
    Returns:
        bool: True if the slot is available, False otherwise
    """
    try:
        # Get the service
        service = get_calendar_service()
        
        # Convert to timezone-aware datetimes
        timezone = pytz.timezone('Asia/Kolkata')
        start = timezone.localize(datetime.combine(date, start_time.time()))
        end = timezone.localize(datetime.combine(date, end_time.time()))
        
        # Format time for API
        time_min = start.isoformat()
        time_max = end.isoformat()
        
        # Check for existing events in the time slot
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # If no events found, the slot is available
        return len(events) == 0
        
    except Exception as e:
        print(f"Error checking time slot availability: {e}")
        return False

def get_available_slots(date: datetime) -> list:
    """
    Get all available time slots for a given date.
    
    Args:
        date: The date to check for available slots
        
    Returns:
        list: List of available time slots as (start, end) tuples
    """
    try:
        # Get the service
        service = get_calendar_service()
        timezone = pytz.timezone('Asia/Kolkata')
        
        # Set up time range for the entire day
        start_of_day = timezone.localize(datetime.combine(date, time(9, 0)))
        end_of_day = timezone.localize(datetime.combine(date, time(18, 0)))
        
        # Get all events for the day
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Initialize with the full day
        available_slots = [(start_of_day, end_of_day)]
        
        # Split available slots based on existing events
        for event in events:
            event_start = parse_datetime(event['start'].get('dateTime', event['start'].get('date')))
            event_end = parse_datetime(event['end'].get('dateTime', event['end'].get('date')))
            
            if not isinstance(event_start, datetime):
                event_start = datetime.combine(event_start, time(0, 0))
            if not isinstance(event_end, datetime):
                event_end = datetime.combine(event_end, time(0, 0))
                
            # Make timezone-aware if not already
            if event_start.tzinfo is None:
                event_start = timezone.localize(event_start)
            if event_end.tzinfo is None:
                event_end = timezone.localize(event_end)
                
            new_slots = []
            for slot_start, slot_end in available_slots:
                # If event overlaps with slot
                if not (event_end <= slot_start or event_start >= slot_end):
                    # Add slot before event
                    if slot_start < event_start:
                        new_slots.append((slot_start, event_start))
                    # Add slot after event
                    if event_end < slot_end:
                        new_slots.append((event_end, slot_end))
                else:
                    new_slots.append((slot_start, slot_end))
            available_slots = new_slots
        
        # Filter out slots that are too short (less than 30 minutes)
        available_slots = [
            (start, end) for start, end in available_slots 
            if (end - start).total_seconds() >= 1800  # 30 minutes in seconds
        ]
        
        return available_slots
        
    except Exception as e:
        print(f"Error getting available slots: {e}")
        return []

def book_slot(
    start_time: datetime,
    end_time: datetime,
    summary: str = "Meeting",
) -> Optional[str]:
    """Book a meeting slot using Google Calendar API"""
    try:
        print(f"Booking slot from {start_time} to {end_time}")
        service = get_calendar_service()
        if not service:
            print("Failed to get calendar service")
            return None
            
        # Make sure times are timezone-aware
        if not start_time.tzinfo:
            start_time = start_time.astimezone(pytz.timezone('Asia/Kolkata'))
        if not end_time.tzinfo:
            end_time = end_time.astimezone(pytz.timezone('Asia/Kolkata'))
        
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'Asia/Kolkata'
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'Asia/Kolkata'
            },
            'reminders': {
                'useDefault': True
            }
        }
        
        print("Creating event...")
        event = service.events().insert(calendarId='primary', body=event).execute()
        print(f"Event created successfully: {event.get('htmlLink')}")
        return event.get('htmlLink')
        
    except Exception as e:
        print(f"Error in book_slot: {e}")
        return None

def check_calendar_events(date: date) -> List[Dict[str, str]]:
    """Check events in calendar using Google Calendar API"""
    try:
        print(f"Checking events for date: {date}")
        service = get_calendar_service()
        if not service:
            return []
            
        start_of_day = datetime.combine(date, datetime.time.min)
        end_of_day = datetime.combine(date, datetime.time.max)
        
        print(f"Querying events from {start_of_day} to {end_of_day}")
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day.isoformat() + 'Z',
            timeMax=end_of_day.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"Found {len(events)} events")
        return events
    except Exception as e:
        print(f"Error checking calendar events: {e}")
        raise

app = FastAPI()

# Add CORS middleware
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Request models
class BookingRequest(BaseModel):
    date: str
    time: str
    summary: Optional[str] = "Meeting"

class AvailabilityRequest(BaseModel):
    date: str
    time: Optional[str] = None

class EventsRequest(BaseModel):
    date: str

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "TailorTalk Calendar API"}

@app.post("/test/book")
async def test_booking(request: BookingRequest):
    """Test booking endpoint for Google Calendar"""
    try:
        print(f"Booking request received: {request.dict()}")
        
        # Parse date and time
        dt, _ = extract_date_time(f"{request.date} {request.time}")
        if not dt:
            raise HTTPException(status_code=400, detail="Invalid date/time format")
            
        # Create 30-minute slot
        start_time = dt
        end_time = dt + timedelta(minutes=30)
        
        print(f"Booking slot from {start_time} to {end_time}")
        
        # Book the slot
        booking_url = book_slot(start_time, end_time, request.summary)
        if not booking_url:
            raise HTTPException(status_code=500, detail="Failed to book slot")
            
        print(f"Booking successful: {booking_url}")
        return {"success": True, "booking_url": booking_url}
        
    except HTTPException as e:
        print(f"HTTP error: {e.detail}")
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test/availability")
async def test_availability(request: AvailabilityRequest):
    """Test availability endpoint for Google Calendar"""
    try:
        print(f"Availability request received: {request.dict()}")
        
        dt, _ = extract_date_time(f"{request.date} {request.time}" if request.time else request.date)
        if not dt:
            raise HTTPException(status_code=400, detail="Invalid date/time format")
            
        slots = suggest_available_slots(
            dt.date(),
            duration_minutes=30,
            start_hour=9,
            end_hour=18
        )
        
        print(f"Found {len(slots)} available slots")
        return {"success": True, "available_slots": slots}
        
    except HTTPException as e:
        print(f"HTTP error: {e.detail}")
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test/events")
async def test_events(request: EventsRequest):
    """Test events endpoint for Google Calendar"""
    try:
        print(f"Events request received: {request.dict()}")
        
        dt, _ = extract_date_time(request.date)
        if not dt:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
        events = check_calendar_events(dt.date())
        print(f"Found {len(events)} events")
        return {"success": True, "events": events}
        
    except HTTPException as e:
        print(f"HTTP error: {e.detail}")
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add OAuth callback endpoint
@app.get("/callback")
async def oauth_callback(code: str):
    """Handle OAuth callback from Google"""
    try:
        print(f"OAuth callback received with code: {code}")
        
        # Force OAuth flow to complete
        get_calendar_service(force_oauth=True)
        return {"success": True, "message": "Authentication successful!"}
    except Exception as e:
        print(f"OAuth error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)