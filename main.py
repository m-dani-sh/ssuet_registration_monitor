
import os
import time
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from twilio.rest import Client
from dotenv import load_dotenv

# --- Load local .env if present ---
load_dotenv()

# --- Config from environment ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP", "whatsapp:+14155238886")
TO_WHATSAPP = os.getenv("TO_WHATSAPP")

# Set to 60 seconds as requested
RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", "60")) 

# Portal Credentials
PORTAL_REG_NO = os.getenv("PORTAL_REG_NO")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD")

# --- Validation ---
if not (GEMINI_API_KEY and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TO_WHATSAPP and PORTAL_REG_NO and PORTAL_PASSWORD):
    print("⚠️ Warning: Missing environment variables. Please check your .env file.")

# --- Configure Gemini ---
genai.configure(api_key=GEMINI_API_KEY)

# --- Twilio client ---
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_whatsapp_message(body_text):
    """Sends a WhatsApp message via Twilio."""
    try:
        message = twilio_client.messages.create(
            from_=FROM_WHATSAPP,
            body=body_text,
            to=TO_WHATSAPP
        )
        print(f"✅ WhatsApp message sent! SID: {message.sid}")
    except Exception as e:
        print(f"‼️ Failed to send WhatsApp message: {e}")

def analyze_page_text(text):
    """Uses strict logic and Gemini AI to determine if registration is OPEN or CLOSED."""
    text_lower = text.lower()
    
    # 1. NEGATIVE KEYWORD CHECK (Highest Priority)
    # If these phrases are found, it's definitely NOT open yet.
    closed_indicators = [
        "active soon", 
        "coming soon", 
        "will be active soon", 
        "registration processes would be active soon",
        "not yet started"
    ]
    if any(indicator in text_lower for indicator in closed_indicators):
        print("🔍 Found 'Coming Soon' indicator. Status: CLOSED")
        return "CLOSED"

    # 2. POSITIVE KEYWORD CHECK
    # Only consider it OPEN if these specific active phrases are found.
    open_keywords = ["register now", "apply online", "select courses", "enrollment active"]
    # Note: We removed "registration open" because it might appear in "registration open soon"
    
    # 3. AI CHECK (Final Decision)
    prompt = f"""
You are a university portal monitor. Determine if course registration is CURRENTLY OPEN or CLOSED.

STRICT RULES:
- If the text says registration will be active "soon", "coming soon", or "in the future", it is CLOSED.
- If the text only talks about "changing passwords" or "preparing for next semester", it is CLOSED.
- It is only OPEN if there is a clear button or link to "Register Now", "Select Courses", or a message saying "Registration is now active".

Respond strictly with one word: OPEN or CLOSED.

Text to analyze:
{text[:4000]}
"""
    try:
        # Using gemini-1.5-flash as it's stable and available
        model = genai.GenerativeModel("gemini-1.5-flash")
        ai_response = model.generate_content(prompt)
        result = ai_response.text.strip().upper()
        
        # Double check AI result against our "soon" rule
        if "OPEN" in result and any(indicator in text_lower for indicator in closed_indicators):
            return "CLOSED"
            
        return "OPEN" if "OPEN" in result else "CLOSED"
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            print("🚨 Gemini API Quota Exceeded! Waiting 10 mins...")
            return "QUOTA_ERROR"
        print(f"Error calling Gemini: {e}")
        return "UNKNOWN"

def check_registration():
    """Logs into the portal and checks the registration status."""
    login_url = "https://edusmartz.ssuet.edu.pk/StudentPortal/Login"
    reg_url = "https://edusmartz.ssuet.edu.pk/studentportal/registration"
    dash_url = "https://edusmartz.ssuet.edu.pk/StudentPortal/Dashboard"
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        print(f"[{time.strftime('%H:%M:%S')}] Checking portal...")
        response = session.get(login_url, timeout=20)
        soup = BeautifulSoup(response.text, "html.parser")
        
        viewstate = soup.find("input", {"name": "__VIEWSTATE"})["value"]
        viewstategen = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})["value"]
        eventvalidation = soup.find("input", {"name": "__EVENTVALIDATION"})["value"]
        
        login_data = {
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstategen,
            "__EVENTVALIDATION": eventvalidation,
            "txtRegistrationNo_cs": PORTAL_REG_NO,
            "txtPassword_m6cs": PORTAL_PASSWORD,
            "btnlgn": "Sign In"
        }
        
        login_response = session.post(login_url, data=login_data, timeout=20)
        
        if "Dashboard" not in login_response.text and "Sign Out" not in login_response.text:
            print("❌ Login failed. Check credentials.")
            return None

        reg_response = session.get(reg_url, timeout=20)
        dash_response = session.get(dash_url, timeout=20)
        
        # Extract text from both pages
        reg_text = BeautifulSoup(reg_response.text, "html.parser").get_text(separator=" ", strip=True)
        dash_text = BeautifulSoup(dash_response.text, "html.parser").get_text(separator=" ", strip=True)
        
        combined_text = reg_text + " " + dash_text
        
        return analyze_page_text(combined_text)

    except Exception as e:
        print(f"Error: {e}")
        return None

def main_loop():
    alerted = False
    
    print(f"🚀 Monitor started. Checking every {RUN_INTERVAL}s")
    
    # --- SELF-TEST ON START ---
    print("Performing self-test...")
    send_whatsapp_message("🤖 Monitor Started! I am now checking your portal every 60 seconds. I will alert you immediately when registration opens.")
    
    while True:
        status = check_registration()
        
        if status == "OPEN":
            if not alerted:
                send_whatsapp_message("🚨 ALERT: Registration is OPEN! Go register now: https://edusmartz.ssuet.edu.pk/studentportal/registration")
                alerted = True
            print("Status: OPEN (Alerted)")
        
        elif status == "CLOSED":
            if alerted:
                print("Status changed back to CLOSED.")
            alerted = False
            print("Status: CLOSED")
            
        elif status == "QUOTA_ERROR":
            print("😴 API exhausted. Sleeping for 10 minutes...")
            time.sleep(600)
            continue

        print(f"Next check in {RUN_INTERVAL} seconds...")
        time.sleep(RUN_INTERVAL)

if __name__ == "__main__":
    main_loop()
