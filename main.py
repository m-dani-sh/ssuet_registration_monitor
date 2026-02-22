import os
import time
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from twilio.rest import Client
from dotenv import load_dotenv

# --- Load local .env if present (for local testing only) ---
load_dotenv()

# --- Config from environment (set these in .env locally OR in Render env vars) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP", "whatsapp:+14155238886")
TO_WHATSAPP = os.getenv("TO_WHATSAPP")
RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", "60"))  # seconds




if not (GEMINI_API_KEY and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TO_WHATSAPP):
    raise SystemExit("Missing required environment variables. Please set GEMINI_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TO_WHATSAPP.")


# --- Configure Gemini ---
genai.configure(api_key=GEMINI_API_KEY)

# --- Twilio client (reuse) ---
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_whatsapp_message(body_text):
    try:
        message = twilio_client.messages.create(
            from_=FROM_WHATSAPP,
            body=body_text,
            to=TO_WHATSAPP
        )
        print("✅ WhatsApp message sent!", message.sid)
    except Exception as e:
        print("‼️ Failed to send WhatsApp message:", e)

def analyze_page_text(text):
    prompt = f"""
You are an intelligent web analyzer.
Based on this webpage text, determine if the registration portal is OPEN or CLOSED.
Look for hints like 'Register Now', 'Apply Online', or 'Registration Closed'.
Respond strictly with one word only — OPEN or CLOSED.

Text:
{text[:5000]}
"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    ai_response = model.generate_content(prompt)
    return ai_response.text.strip().upper()

def check_registration():
    url = "https://edusmartz.ssuet.edu.pk/studentportal/registration"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print("Error fetching page:", e)
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    cleaned_text = soup.get_text(separator=" ", strip=True)
    try:
        result = analyze_page_text(cleaned_text)
        print("Gemini Output:", result)
        print("cleaned_text",cleaned_text)
        # send_whatsapp_message("🎉 Registration is OPEN! Go register your courses now: https://edusmartz.ssuet.edu.pk/studentportal/registration")


        return result
    except Exception as e:
        print("Error calling Gemini:", e)
        return None

def main_loop():
    alerted = False  # tracks whether we've already notified for current OPEN state
    while True:
        try:
            status = check_registration()
            if status == "OPEN":
                if not alerted:
                    send_whatsapp_message("🎉 Registration is OPEN! Go register your courses now: https://edusmartz.ssuet.edu.pk/studentportal/registration")
                    alerted = True
                else:
                    print("Already alerted — still OPEN.")
            elif status == "CLOSED":
                if alerted:
                    print("State changed to CLOSED. Resetting alert flag.")
                alerted = False
            else:
                # status is None or unexpected
                print("Status unknown; will retry.")
        except Exception as e:
            print("Unhandled error in main loop:", e)
        time.sleep(RUN_INTERVAL)

if __name__ == "__main__":
    print("Starting registration monitor. Interval:", RUN_INTERVAL, "seconds")
    main_loop()
