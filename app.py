import requests
import time
import threading
from flask import Flask

# Flask-server för att göra Render nöjd och hålla tjänsten vaken
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Arvikamagasinets Polislyssnare är igång!", 200

# Polisens öppna API för aktuella händelser
POLISEN_API_URL = "https://polisen.se/api/events"

# Din unika Webhook från Make.com
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/dhf763wasxaqirnhh7io0axsmkw2yttb"

# Sökord som måste finnas i rubriken eller brödtexten
KEYWORDS = ["arvika", "eda", "årjäng", "värmland"]

seen_event_ids = set()

def check_police_events():
    while True:
        try:
            response = requests.get(POLISEN_API_URL, timeout=10)
            if response.status_code == 200:
                events = response.json()
                
                for event in events:
                    event_id = event.get("id")
                    
                    # Hoppa över om vi redan behandlat denna händelse
                    if event_id in seen_event_ids:
                        continue
                    
                    name = event.get("name", "").lower()
                    summary = event.get("summary", "").lower()
                    
                    # Kolla om något av dina sökord finns med
                    is_match = any(word in name or word in summary for word in KEYWORDS)
                    
                    if is_match:
                        # Bygg JSON-paketet som skickas direkt till Make.com
                        payload = {
                            "id": event_id,
                            "title": event.get("name"),
                            "summary": event.get("summary"),
                            "url": "https://polisen.se" + event.get("url", ""),
                            "type": event.get("type"),
                            "datetime": event.get("datetime"),
                            "location": event.get("location", {}).get("name")
                        }
                        
                        # Skicka till Make (0 sekunders fördröjning)
                        requests.post(MAKE_WEBHOOK_URL, json=payload)
                    
                    # Spara ID så vi undviker dubbletter
                    seen_event_ids.add(event_id)
                
                # Rensa minnet om listan blir för stor
                if len(seen_event_ids) > 500:
                    seen_event_ids.clear()
                    
        except Exception as e:
            print(f"Fel vid hämtning från Polisens API: {e}")
        
        # Vänta 30 sekunder innan nästa avläsning
        time.sleep(30)

# Starta polislyssnaren i en bakgrundstråd
thread = threading.Thread(target=check_police_events, daemon=True)
thread.start()
