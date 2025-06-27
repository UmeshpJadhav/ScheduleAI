import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.messages import HumanMessage, AIMessage
import re
from datetime import datetime, timedelta, time, date
from calendar_utils import (
    suggest_available_slots,
    get_calendar_service,
    book_slot,
    extract_date_time,
    check_calendar_events,
    is_time_slot_available,
    get_available_slots
)
from typing import Optional, Tuple, List, Dict, Any
import pytz


load_dotenv()


llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    #temperature=0.7,  
)


session_state = {
    'intent': None,
    'date': None,
    'time': None,
    'slots': [], 
    'slot_selected': None,
    'confirmed': False,
    'context': [],  
    'waiting_for_slot': False, 
    'selected_date': None
}

def reset_session():
    session_state.update({
        'intent': None,
        'date': None,
        'time': None,
        'slots': [],
        'slot_selected': None,
        'confirmed': False,
        'context': [],
        'waiting_for_slot': False,
        'selected_date': None
    })

def detect_intent(message: str) -> str:
    """Detect the user's intent from the message"""
    message_lower = message.lower()
    
  
    cancel_keywords = ['cancel', 'delete', 'remove', 'reschedule']
    meeting_keywords = ['meeting', 'appointment', 'event', 'call']
    
    if any(word in message_lower for word in cancel_keywords) and \
       any(word in message_lower for word in meeting_keywords):
        return "cancel meeting"
    
    
    booking_keywords = ['book', 'schedule', 'set up', 'create', 'new']
    if any(word in message_lower for word in booking_keywords):
        return "book meeting"
        
   
    availability_keywords = ['available', 'free', 'open', 'when are you free']
    if any(word in message_lower for word in availability_keywords):
        return "check availability"
        
   
    calendar_keywords = ['calendar', 'agenda', 'schedule', 'what do i have']
    if any(word in message_lower for word in calendar_keywords):
        return "view calendar"
        
   
    return "general"

def get_intent(message: str) -> str:
    """Determine user's intent using keyword matching and context"""
    message = message.lower()
    
    intent = detect_intent(message)
    
    if session_state.get('waiting_for_slot', False):
        time_related = any(word in message for word in ["between", "at", "on", "tomorrow", "today", "monday", "tuesday", 
                                                      "wednesday", "thursday", "friday", "saturday", "sunday", "am", "pm"])
        if time_related and not message.strip().isdigit():
            session_state['waiting_for_slot'] = False
    
    if intent == "cancel meeting":
        return intent
    
    if any(keyword in message for keyword in ["book", "schedule", "meeting", "appointment"]):
        return "book meeting"
    if any(keyword in message for keyword in ["available", "slots", "time", "when"]):
        return "check availability"
    if any(keyword in message for keyword in ["cancel", "remove", "delete"]):
        return "cancel meeting"
    if any(keyword in message for keyword in ["view", "show", "list", "calendar"]):
        return "check calendar"
    
    if session_state.get('waiting_for_slot', False):
        try:
            slot_num = int(message.strip())
            if 1 <= slot_num <= len(session_state.get('slots', [])):
                return "confirm slot"
        except ValueError:
            pass
    
    if any(keyword in message for keyword in ["january", "february", "march", "april", "may", "june", 
                                             "july", "august", "september", "october", "november", "december"]):
        return "book meeting"
    
    return "general conversation"

def handle_calendar_action(intent: str, message: str) -> str:
    """Handle calendar-specific actions with improved conversation flow"""
    intent = intent.lower()
    
    if intent == "confirm slot" or session_state.get('waiting_for_slot', False):
        return confirm_slot(message)
        
    if intent == "check availability":
        return check_availability_flow(message)
    elif intent == "book meeting":
        dt, time_obj = extract_date_time(message)
        if dt and time_obj:
            return book_meeting_flow(message)
        elif dt:
            return check_availability_flow(message)
        else:
            return "I'd be happy to help you book a meeting. Could you please tell me when you'd like to schedule it?"
    elif intent == "cancel meeting":
        return handle_cancel_request(message)
    elif intent == "check calendar":
        return check_calendar(message)
    
    return "I'm not sure how to help with that. I can help you book meetings, check availability, or view your calendar."

def handle_default_response(message: str) -> str:
    """Handle default conversation flow with enhanced context awareness and natural responses"""
    try:
        chat_history = []
        for i in range(0, len(session_state.get('context', [])), 2):
            if i + 1 < len(session_state['context']):
                chat_history.append((session_state['context'][i].content, session_state['context'][i+1].content))
        
        system_message = """You are TailorTalk Assistant, a friendly and professional calendar scheduling bot. 
Your goal is to help users manage their calendar, book meetings, and check availability.

Guidelines:
- Be warm, concise, and helpful
- Use natural language and emojis when appropriate
- If you need more information, ask specific questions
- When confirming actions, summarize the details
- Keep responses brief and to the point
- Use markdown for better readability

You can help with:
- Booking meetings
- Checking availability
- Viewing calendar events
- Managing existing bookings"""
        
        messages = [("system", system_message)]
        
        for user_msg, ai_msg in chat_history[-4:]:
            messages.extend([
                ("user", user_msg),
                ("assistant", ai_msg)
            ])
        
        current_context = f"""Current context:
- User's timezone: Asia/Kolkata
- Current time: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}

User's message: {message}"""
        
        messages.append(("user", current_context))
        
        template = ChatPromptTemplate.from_messages([
            (role, content) for role, content in messages
        ])
        
        chain = template | llm
        response = chain.invoke({})
        
        response_text = response.content.strip()
        
        session_state.setdefault('context', []).append(AIMessage(content=response_text))
        
        return response_text
        
    except Exception as e:
        print(f"Error in handle_default_response: {str(e)}")
        return "I apologize, but I'm having trouble processing your request. Could you please rephrase or try again?"

def format_calendar_response(events: list) -> str:
    """Format calendar events into a natural language response"""
    if not events:
        return "You don't have any events scheduled for this time."
    
    response = ["Here's what I found on your calendar:"]
    
    for i, event in enumerate(events, 1):
        start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')))
        end = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date')))
        
        time_str = f"{start.strftime('%I:%M %p').lstrip('0')} - {end.strftime('%I:%M %p').lstrip('0')}"
            
        response.append(f"{i}.  *{event.get('summary', 'No title')}*")
        response.append(f"    {start.strftime('%A, %B %d, %Y')}" + 
                      f" at {time_str}")
        
        if 'location' in event:
            response.append(f"    {event['location']}")
        if 'description' in event:
            desc = event['description'][:100] + '...' if len(event['description']) > 100 else event['description']
            response.append(f"    {desc}")
        response.append("")
    
    return "\n".join(response)

def check_availability_flow(message: str) -> str:
    """Handle the availability checking flow with improved conversation handling"""
    try:
        dt, time_obj = extract_date_time(message)
        
        if not dt:
            return "I'd be happy to check my availability. Could you please tell me which date and time you're interested in?"
            
        if ("between" in message.lower() and "and" in message.lower()) or "-" in message:
            try:
                time_pattern = r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)\s*(?:-|to|and)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)'
                matches = re.search(time_pattern, message, re.IGNORECASE)
                if matches:
                    start_time_str, end_time_str = matches.groups()
                    date_str = dt.strftime('%B %d, %Y').lstrip('0').replace(' 0', ' ')
                    return book_meeting_flow(f"{date_str} from {start_time_str} to {end_time_str}")
            except Exception as e:
                print(f"Error parsing time range: {e}")
        
        if time_obj:
            if not (datetime.time(9, 0) <= time_obj.time() < datetime.time(18, 0)):
                return f"I'm only available between 9 AM and 6 PM. Would you like to pick another time?"
                
            available = is_time_slot_available(dt, time_obj, time_obj.replace(hour=time_obj.hour + 1))
            if available:
                time_str = time_obj.strftime('%I:%M %p').lstrip('0')
                return f"Yes, I'm available on {dt.strftime('%A, %B %d, %Y')} at {time_str}. Would you like to book this time?"
            else:
                time_str = time_obj.strftime('%I:%M %p').lstrip('0')
                return f"I'm sorry, I'm not available at {time_str} on {dt.strftime('%A, %B %d')}. Would you like to check another time?"
        
        available_slots = get_available_slots(dt)
        
        if not available_slots:
            return f"I don't have any available slots on {dt.strftime('%A, %B %d, %Y')}. Would you like to check another day?"
        
        session_state['slots'] = available_slots
        session_state['selected_date'] = dt
        session_state['waiting_for_slot'] = True
        
        response = [f"I'm available on {dt.strftime('%A, %B %d, %Y')} at the following times:"]
        for i, slot in enumerate(available_slots, 1):
            start = slot[0].strftime('%I:%M %p').lstrip('0')
            end = slot[1].strftime('%I:%M %p').lstrip('0')
            response.append(f"{i}. {start} - {end}")
        
        response.append("\nPlease let me know which time slot works best for you by entering the number, or suggest another time that might work better for you.")
        
        return "\n".join(response)
        
    except Exception as e:
        print(f"Error in check_availability_flow: {e}")
        import traceback
        traceback.print_exc()
        return "I'm sorry, I encountered an error while checking availability. Could you please try again?"

def book_meeting_flow(message: str) -> str:
    """Handle meeting booking flow with improved time range parsing"""
    try:
        print(f"Processing booking request: {message}")
        
        time_range_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(?:am|pm|AM|PM)?\s*(?:-|to|until|through|thru|\s)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?'
        time_match = re.search(time_range_pattern, message, re.IGNORECASE)
        
        if time_match:
            start_hr = int(time_match.group(1))
            start_min = int(time_match.group(2) or 0)
            end_hr = int(time_match.group(3))
            end_min = int(time_match.group(4) or 0)
            
            period = (time_match.group(5) or '').lower()
            if 'pm' in period or 'PM' in period:
                if end_hr < 12:
                    end_hr += 12
            
            if 'pm' in message.lower() and start_hr < 12 and not ('am' in message.lower() and 'pm' in message.lower()):
                start_hr += 12
            if 'pm' in message.lower() and end_hr < 12 and not ('am' in message.lower() and 'pm' in message.lower()):
                end_hr += 12
            if 'am' in message.lower() and start_hr == 12:
                start_hr = 0
            if 'am' in message.lower() and end_hr == 12:
                end_hr = 0
                
            dt, _ = extract_date_time(message)
            if not dt:
                return "I couldn't determine the date. Please include a date with your request."
                
            start_dt = dt.replace(hour=start_hr, minute=start_min, second=0, microsecond=0)
            end_dt = dt.replace(hour=end_hr, minute=end_min, second=0, microsecond=0)
            
            if end_hr < start_hr:
                end_dt += timedelta(days=1)
                
            print(f"Booking time range: {start_dt} to {end_dt}")
            
            if not is_time_slot_available(dt, start_dt, end_dt):
                start_time = start_dt.strftime('%I:%M %p').lstrip('0')
                end_time = end_dt.strftime('%I:%M %p').lstrip('0')
                date_str = dt.strftime('%A, %B %d')
                return f"I'm sorry, I'm not available from {start_time} to {end_time} on {date_str}. Would you like to try another time?"
            
            event_link = book_slot(start_dt, end_dt, "Meeting")
            if event_link:
                start_time = start_dt.strftime('%I:%M %p').lstrip('0')
                end_time = end_dt.strftime('%I:%M %p').lstrip('0')
                date_str = dt.strftime('%A, %B %d')
                return f"I've successfully booked your meeting from {start_time} to {end_time} on {date_str}. Here's your calendar event: {event_link}"
            else:
                return "I'm sorry, I couldn't book your meeting. Please try again later."
        
        dt, time_obj = extract_date_time(message)
        if not dt:
            return "I couldn't understand the date/time you provided. Please try again."
            
        if not time_obj:
            return check_availability_flow(message)
            
        start_dt = dt.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)
        
        if not is_time_slot_available(dt, start_dt, end_dt):
            time_str = time_obj.strftime('%I:%M %p').lstrip('0')
            date_str = dt.strftime('%A, %B %d')
            return f"I'm sorry, I'm not available at {time_str} on {date_str}. Would you like to try another time?"
        
        event_link = book_slot(start_dt, end_dt, "Meeting")
        if not event_link:
            return "Failed to book the slot. Please try again."
            
        return f" Meeting booked successfully!\n Date: {start_dt.strftime('%A, %B %d, %Y')}\n Time: {start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}\n\n {event_link}"
            
    except Exception as e:
        print(f"Error in book_meeting_flow: {e}")
        return "I'm sorry, I encountered an error while processing your request. Please try again."

def handle_cancel_request(message: str) -> str:
    """Handle meeting cancellation requests"""
    try:
        dt, _, _ = extract_datetime_with_gemini(message)
        
        if not dt:
            dt, _ = extract_date_time(message)
        
        if not dt:
            dt = datetime.now(pytz.timezone('Asia/Kolkata')).date()
        
        service = get_calendar_service()
        events = get_events_for_date(service, dt)
        
        if not events:
            return f"No meetings found for {dt.strftime('%A, %B %d, %Y')} to cancel."
        
        if len(events) == 1:
            event = events[0]
            event_id = event['id']
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            return f" Successfully cancelled your meeting: {event.get('summary', 'Untitled event')} on {dt.strftime('%A, %B %d, %Y')}"
        
        events_list = "\n".join([
            f"{i+1}. {e.get('summary', 'Untitled event')} at "
            f"{datetime.fromisoformat(e['start'].get('dateTime', e['start'].get('date'))).strftime('%I:%M %p').lstrip('0')}"
            for i, e in enumerate(events)
        ])
        
        return (
            f"I found multiple meetings on {dt.strftime('%A, %B %d, %Y')}:\n"
            f"{events_list}\n\n"
            "Please specify which meeting you'd like to cancel by number or name."
        )
        
    except Exception as e:
        print(f"Error in handle_cancel_request: {e}")
        return "I encountered an error while trying to cancel your meeting. Please try again."

def get_events_for_date(service, date_obj):
    """Get all events for a specific date"""
    try:
        tz = pytz.timezone('Asia/Kolkata')
        start_dt = datetime.combine(date_obj, time.min).astimezone(tz)
        end_dt = datetime.combine(date_obj, time.max).astimezone(tz)
        
        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_str,
            timeMax=end_str,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return events_result.get('items', [])
        
    except Exception as e:
        print(f"Error in get_events_for_date: {e}")
        return []

def check_calendar(message: str) -> str:
    """Check calendar events for a specific date"""
    try:
        dt, _ = extract_date_time(message)
        if not dt:
            return "I couldn't understand the date you provided. Please try again."
            
        events = check_calendar_events(dt.date())
        
        if not events:
            return "No events found on this date."
            
        event_texts = []
        for event in events:
            start = datetime.datetime.fromisoformat(event['start']['dateTime'])
            end = datetime.datetime.fromisoformat(event['end']['dateTime'])
            event_texts.append(f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}: {event['summary']}")
        
        return f"Events for {dt.strftime('%A, %B %d, %Y')}:\n{'\n'.join(event_texts)}"
        
    except Exception as e:
        return f"Error checking calendar: {str(e)}"

def confirm_slot(message: str) -> str:
    """Handle slot confirmation"""
    try:
        slot_num = int(message.strip())
        if slot_num < 1 or slot_num > len(session_state['slots']):
            return "Invalid slot number. Please select a valid slot."
            
        start_time, end_time = session_state['slots'][slot_num - 1]
        
        booking_url = book_slot(start_time, end_time, "Meeting")
        if not booking_url:
            return "Failed to book the slot. Please try again."
            
        return f" Meeting booked successfully!\n Date: {start_time.strftime('%A, %B %d, %Y')}\n Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}\n\n {booking_url}"
        
    except ValueError:
        return "Please enter a valid slot number."
    except Exception as e:
        return f"Error confirming slot: {str(e)}"

def extract_datetime_with_gemini(message: str) -> Tuple[Optional[datetime], Optional[time], str]:
    """
    Use Gemini to extract date and time from natural language.
    Returns a tuple of (datetime, time, extracted_text)
    """
    try:
        current_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        prompt = f"""
        Extract the exact date and time from the user's message. 
        
        Rules:
        1. If only time is mentioned, assume today's date
        2. If only date is mentioned, return just the date
        3. Use 24-hour format for times
        4. If date is not specified, use today or the next occurrence
        5. Current date and time: {current_time.strftime('%Y-%m-%d %H:%M')} IST
        
        User's message: "{message}"
        
        Respond ONLY with the extracted date and time in this exact format:
        [DATE_TIME]
        Date: YYYY-MM-DD
        Time: HH:MM (24h format)
        [/DATE_TIME]
        
        Example 1: "Book a meeting tomorrow afternoon"
        [DATE_TIME]
        Date: {current_time.year}-{current_time.month:02d}-{(current_time + timedelta(days=1)).day:02d}
        Time: 15:00
        [/DATE_TIME]
        
        Example 2: "Schedule for June 30 at 11:30"
        [DATE_TIME]
        Date: {current_time.year}-06-30
        Time: 11:30
        [/DATE_TIME]
        """
        
        print(f"Sending to Gemini: {prompt}")
        
        response = llm.invoke(prompt)
        extracted_text = response.content.strip()
        print(f"Gemini raw response: {extracted_text}")
        
        date_match = re.search(r'Date:\s*(\d{4}-\d{2}-\d{2})', extracted_text)
        time_match = re.search(r'Time:\s*(\d{1,2}:\d{2})', extracted_text)
        
        dt_obj = None
        time_obj = None
        
        if date_match or time_match:
            date_str = date_match.group(1) if date_match else current_time.strftime('%Y-%m-%d')
            time_str = time_match.group(1) if time_match else None
            
            try:
                dt_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                if time_str:
                    time_obj = datetime.strptime(time_str, '%H:%M').time()
                
                print(f"Parsed - Date: {dt_obj}, Time: {time_obj}")
                return dt_obj, time_obj, extracted_text
                
            except Exception as e:
                print(f"Error parsing date/time: {e}")
        
        dt, t = extract_date_time(message)
        return dt, t, message
        
    except Exception as e:
        print(f"Error in extract_datetime_with_gemini: {e}")
        dt, t = extract_date_time(message)
        return dt, t, message

def handle_booking_request(message: str) -> str:
    """Handle booking requests with Gemini-powered date/time extraction"""
    try:
        dt, t, extracted_text = extract_datetime_with_gemini(message)
        
        print(f"Extracted - Date: {dt}, Time: {t}, Text: {extracted_text}")
        
        if dt is None and t is None:
            return "I couldn't find a specific date or time in your request. Could you please provide more details?"
            
        if t is not None:
            if dt is None:  
                dt = datetime.now(pytz.timezone('Asia/Kolkata')).date()
            
            booking_dt = datetime.combine(dt, t)
            
            formatted_time = t.strftime("%I:%M %p").lstrip('0')
            formatted_date = dt.strftime("%A, %B %d, %Y")
            
            if is_time_slot_available(booking_dt, 30):  
                return f"I can book a meeting for you on {formatted_date} at {formatted_time}. Would you like to confirm?"
            else:
                return f"I'm sorry, the slot on {formatted_date} at {formatted_time} is not available. Would you like to see available slots?"
        
        elif dt is not None:
            available_slots = get_available_slots(dt)
            
            if available_slots:
                slots_text = "\n".join([
                    f"{i+1}. {s['start'].strftime('%I:%M %p').lstrip('0')} - {s['end'].strftime('%I:%M %p').lstrip('0')}" 
                    for i, s in enumerate(available_slots)
                ])
                return f"Here are the available time slots on {dt.strftime('%A, %B %d, %Y')}:\n{slots_text}\n\nPlease select a slot by number."
            else:
                return f"I'm sorry, there are no available slots on {dt.strftime('%A, %B %d, %Y')}."
        
    except Exception as e:
        print(f"Error in handle_booking_request: {e}")
        return "I encountered an error while processing your request. Please try again."

def process_user_message(message: str) -> str:
    """Process user message and return response with improved conversation handling"""
    try:
        if 'context' not in session_state:
            session_state['context'] = []
            
        session_state['context'].append(HumanMessage(content=message))
        
        intent = get_intent(message)
        session_state['intent'] = intent
        
        if intent == "confirm slot" and session_state.get('waiting_for_slot', False):
            response = confirm_slot(message)
            session_state['waiting_for_slot'] = False
        elif intent.lower() in ["check availability", "book meeting", "cancel meeting", "check calendar"]:
            response = handle_calendar_action(intent, message)
        elif intent.lower() == "book meeting":
            response = handle_booking_request(message)
        else:
            response = handle_default_response(message)
        
        if not isinstance(response, str):
            response = str(response)
            
        session_state['context'].append(AIMessage(content=response))
        
        if len(session_state['context']) > 10:  
            session_state['context'] = session_state['context'][-10:]
            
        return response
        
    except Exception as e:
        error_msg = f"I'm sorry, I encountered an error: {str(e)}"
        print(f"Error in process_user_message: {error_msg}")
        return "I apologize, but I'm having trouble processing your request. Could you please try again?"

def main():
    print(process_user_message("Book a meeting tomorrow afternoon"))

if __name__ == "__main__":
    main()