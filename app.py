import requests
import time
import threading
import os
import re
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Arvikamagasinets Polislyssnare är igång!", 200

POLISEN_API_URL = "https://polisen.se/api/events"

# Hämtar länken säkert från Renders inställningar
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL")

# Specifika kommuner och orter i bevakningsområdet
TARGET_LOCATIONS = [
    "arvika", "eda", "årjäng", "töcksfors", 
    "charlottenberg", "jössefors", "klässbol", "sulvik"
]

seen_event_ids = set()

def matches_target_location(text):
    """
    Kollar om någon av orterna finns som ett FRISTÅENDE ord i texten.
    Säkerställer att t.ex. 'eda' inte matchar 'nedan' eller 'fredag'.
    """
    text_lower = text.lower()
    for loc in TARGET_LOCATIONS:
        # \b står för word boundary (ordgräns)
        if re.search(rf"\b{re.escape(loc)}\b", text_lower):
            return True
    return False

def check_police_events():
    while True:
        try:
            # Om inte miljövariabeln är satt än, vänta
            if not MAKE_WEBHOOK_URL:
                print("Väntar på att MAKE_WEBHOOK_URL ska konfigureras...")
                time.sleep(10)
                continue

            response = requests.get(POLISEN_API_URL, timeout=10)
            if response.status_code == 200:
                events = response.json()
                
                for event in events:
                    event_id = event.get("id")
                    
                    if event_id in seen_event_ids:
                        continue
                    
                    name = event.get("name", "")
                    summary = event.get("summary", "")
                    location_name = event.get("location", {}).get("name", "")
                    
                    # 1. Matchar orter i titel, sammanfattning eller plats-fältet
                    is_match = (
                        matches_target_location(name) or 
                        matches_target_location(summary) or 
                        matches_target_location(location_name)
                    )
                    
                    if is_match:
                        payload = {
                            "id": event_id,
                            "title": event.get("name"),
                            "summary": event.get("summary"),
                            "url": "https://polisen.se" + event.get("url", ""),
                            "type": event.get("type"),
                            "datetime": event.get("datetime"),
                            "location": event.get("location", {}).get("name")
                        }
                        requests.post(MAKE_WEBHOOK_URL, json=payload)
                    
                    seen_event_ids.add(event_id)
                
                if len(seen_event_ids) > 500:
                    seen_event_ids.clear()
                    
        except Exception as e:
            print(f"Fel vid hämtning: {e}")
        
        time.sleep(30)

thread = threading.Thread(target=check_police_events, daemon=True)
thread.start()
