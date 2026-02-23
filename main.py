import os
import time
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from twilio.rest import Client
from dotenv import load_dotenv

# ================= LOAD ENV =================
load_dotenv()

# ================= GEMINI MULTI-ACCOUNT KEYS =================
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
]

# Remove empty keys
GEMINI_KEYS = [key for key in GEMINI_KEYS if key]

print(f"🔑 Loaded {len(GEMINI_KEYS)} Gemini API Keys (Different Accounts)")

# ================= TWILIO CONFIG =================
TWILIO_ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP", "whatsapp:+14155238886")
TO_WHATSAPP = os.getenv("TO_WHATSAPP")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ================= PORTAL CONFIG =================
PORTAL_REG_NO = os.getenv("PORTAL_REG_NO")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD")

RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", "60"))


# ================= GEMINI ROTATION FUNCTION =================
def call_gemini_with_rotation(prompt):
    """
    Try each Gemini key sequentially.
    If one fails (quota/429), move to next.
    If all fail, return ALL_KEYS_FAILED.
    """

    for index, api_key in enumerate(GEMINI_KEYS):
        try:
            print(f"🔑 Trying Gemini Key #{index + 1}")

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            response = model.generate_content(prompt)
            result = response.text.strip().upper()

            print(f"✅ Success with Key #{index + 1}")
            return result

        except Exception as e:
            error_msg = str(e).lower()

            if "429" in error_msg or "quota" in error_msg or "api key" in error_msg:
                print(f"🚨 Key #{index + 1} quota exhausted. Switching...")
                continue  # try next key
            else:
                print(f"❌ Non-quota error: {e}")
                return "UNKNOWN"

    print("💀 All Gemini keys from all accounts failed!")
    return "ALL_KEYS_FAILED"


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

    # 1️⃣ Strong CLOSED indicators
    closed_indicators = [
        "active soon",
        "coming soon",
        "will be active soon",
        "not yet started"
    ]

    if any(indicator in text_lower for indicator in closed_indicators):
        print("🔍 Found 'Coming Soon' → CLOSED")
        return "CLOSED"

    # 2️⃣ Strong OPEN keywords (save API quota)
    open_keywords = ["register now", "select courses", "enrollment active", "apply online"]

    if any(keyword in text_lower for keyword in open_keywords):
        print("⚡ OPEN keyword detected (No AI needed)")
        return "OPEN"

    # 3️⃣ AI Check (Only if needed)
    prompt = f"""
You are a university portal monitor.

If registration is currently active and students can register now, reply OPEN.
If registration is not active or coming soon, reply CLOSED.

Reply with only one word:
OPEN or CLOSED

Text:
{text[:4000]}
"""

    result = call_gemini_with_rotation(prompt)

    # 4️⃣ Fallback if all keys fail
    if result == "ALL_KEYS_FAILED" or result == "UNKNOWN":
        print("🛡️ Using Rule-Based Fallback")
        if any(keyword in text_lower for keyword in open_keywords):
            return "OPEN"
        return "CLOSED"

    if "OPEN" in result:
        return "OPEN"

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