import os
import time
import requests
from bs4 import BeautifulSoup
from twilio.rest import Client
from dotenv import load_dotenv

# ================= LOAD ENV =================
load_dotenv()

# ================= TWILIO CONFIG =================
TWILIO_ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP", "whatsapp:+14155238886")
TO_WHATSAPP = os.getenv("TO_WHATSAPP")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ================= PORTAL CONFIG =================
PORTAL_REG_NO =  os.getenv("PORTAL_REG_NO")
PORTAL_PASSWORD =  os.getenv("PORTAL_PASSWORD")

RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", "60"))


# ================= WHATSAPP FUNCTION =================
def send_whatsapp_message(body_text):
    try:
        message = twilio_client.messages.create(
            from_=FROM_WHATSAPP,
            body=body_text,
            to=TO_WHATSAPP
        )
        print(f"✅ WhatsApp sent! SID: {message.sid}")

    except Exception as e:
        print(f"‼️ WhatsApp error: {e}")


# ================= ANALYSIS FUNCTION =================
def analyze_page_text(text):
    text_lower = text.lower()

    # Strong CLOSED indicators
    closed_indicators = [
        "active soon",
        "coming soon",
        "will be active soon",
        "not yet started",
        "registration is closed"
    ]

    if any(indicator in text_lower for indicator in closed_indicators):
        print("🔍 Found CLOSED indicator → CLOSED")
        return "CLOSED"

    # Strong OPEN keywords
    open_keywords = [
        "register now",
        "select courses",
        "enrollment active",
        "apply online",
        "min credit hours",
        "max credit hours",
        "course code",
        "course type",
        "section",
        "available seats"
    ]

    if any(keyword in text_lower for keyword in open_keywords):
        print("⚡ OPEN keyword detected")
        return "OPEN"
    
    # Fallback to CLOSED if no strong indicators are found
    print("🛡️ No strong OPEN indicators found, defaulting to CLOSED")
    return "CLOSED"


# ================= PORTAL CHECK =================
def check_registration():
    login_url = "https://edusmartz.ssuet.edu.pk/StudentPortal/Login"
    reg_url = "https://edusmartz.ssuet.edu.pk/studentportal/registration"
    dash_url = "https://edusmartz.ssuet.edu.pk/StudentPortal/Dashboard"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
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
            print("❌ Login failed!")
            return None

        reg_response = session.get(reg_url, timeout=20)
        dash_response = session.get(dash_url, timeout=20)

        reg_text = BeautifulSoup(reg_response.text, "html.parser").get_text(" ", strip=True)
        dash_text = BeautifulSoup(dash_response.text, "html.parser").get_text(" ", strip=True)

        combined_text = reg_text + " " + dash_text
        # print("🔍 Analyzing page content...")
        # print(f"📄 Combined text length: {len(combined_text)}")
        # print(f"📄 Sample text snippet: {combined_text}")

        return analyze_page_text(combined_text)

    except Exception as e:
        print(f"❌ Portal error: {e}")
        return None


# ================= MAIN LOOP =================
def main_loop():

    alerted = False

    print(f"🚀 Monitor started. Checking every {RUN_INTERVAL} seconds")

    send_whatsapp_message(
        "🤖 Registration Monitor Started!\nI will check every 60 seconds and alert you instantly."
    )

    while True:
        status = check_registration()

        if status == "OPEN":
            if not alerted:
                send_whatsapp_message(
                    "🚨 ALERT: Registration is OPEN!\nhttps://edusmartz.ssuet.edu.pk/studentportal/registration"
                )
                alerted = True
            print("🟢 Status: OPEN (Alert sent)")

        elif status == "CLOSED":
            alerted = False
            print("🔴 Status: CLOSED")

        else:
            print("⚠️ Status: UNKNOWN")

        print(f"⏱️ Next check in {RUN_INTERVAL} seconds...\n")
        time.sleep(RUN_INTERVAL)


if __name__ == "__main__":
    main_loop()
