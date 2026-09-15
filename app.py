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
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL")

# Sökord som måste matcha som exakta, fristående ord
KEYWORDS = ["arvika", "eda", "årjäng", "värmland"]

seen_event_ids = set()

def matches_keyword(text):
    """
    Kollar om något av sökorden finns som ett FRISTÅENDE ord i texten.
    Säkerställer att 'eda' inte matchar 'nedan' eller 'fredag'.
    """
    if not text:
        return False
    text_lower = text.lower()
    for kw in KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            return True
    return False

def check_police_events():
    is_first_run = True  # Förhindrar att gamla notiser skickas igen vid omstart av Render

    while True:
        try:
            if not MAKE_WEBHOOK_URL:
                print("Väntar på att MAKE_WEBHOOK_URL ska konfigureras...")
                time.sleep(10)
                continue

            response = requests.get(POLISEN_API_URL, timeout=10)
            if response.status_code == 200:
                events = response.json()
                
                for event in events:
                    event_id = event.get("id")
                    
                    # Hoppa över om vi redan hanterat händelsen
                    if event_id in seen_event_ids:
                        continue
                    
                    # Vid första körningen (omstart) sparar vi bara ID:t tyst i minnet
                    if is_first_run:
                        seen_event_ids.add(event_id)
                        continue

                    name = event.get("name", "")
                    summary = event.get("summary", "")
                    location_name = event.get("location", {}).get("name", "")
                    
                    # Träff om Arvika, Eda, Årjäng eller Värmland finns som fristående ord
                    is_match = (
                        matches_keyword(name) or 
                        matches_keyword(summary) or 
                        matches_keyword(location_name)
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
                
                # Efter första varvet börjar skriptet skicka webhooks för nya händelser
                is_first_run = False

                # Säkert minnesskydd
                if len(seen_event_ids) > 2000:
                    seen_event_ids_list = list(seen_event_ids)
                    seen_event_ids.clear()
                    seen_event_ids.update(seen_event_ids_list[1000:])
                    
        except Exception as e:
            print(f"Fel vid hämtning: {e}")
        
        time.sleep(30)

thread = threading.Thread(target=check_police_events, daemon=True)
thread.start()
