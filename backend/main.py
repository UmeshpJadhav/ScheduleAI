from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, date, time, timedelta
from calendar_utils import (
    suggest_available_slots,
    book_slot,
    check_calendar_events,
    get_calendar_service,
    extract_date_time
)
from agent import process_user_message

app = FastAPI()


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "TailorTalk Calendar API"}

@app.post("/test/book")
async def test_booking(request: BookingRequest):
    """Test booking endpoint for Google Calendar"""
    try:
        print(f"Booking request received: {request.dict()}")
        
        
        dt, _ = extract_date_time(f"{request.date} {request.time}")
        if not dt:
            raise HTTPException(status_code=400, detail="Invalid date/time format")
            
        
        start_time = dt
        end_time = dt + timedelta(minutes=30)
        
        print(f"Booking slot from {start_time} to {end_time}")
        

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

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Handle chat messages from frontend"""
    try:
        response = process_user_message(request.message)
        return {"response": response}
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/callback")
async def oauth_callback(code: str):
    """Handle OAuth callback from Google"""
    try:
        print(f"OAuth callback received with code: {code}")
        
        
        get_calendar_service(force_oauth=True)
        return {"success": True, "message": "Authentication successful!"}
    except Exception as e:
        print(f"OAuth error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)