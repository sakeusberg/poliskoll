import requests
import time
import threading
import os
import re
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Arvikamagasinets Bevakningsbot (Polis & Trafikverket) är igång!", 200

# --- KONFIGURATION & MILJÖVARIABLER ---
POLISEN_API_URL = "https://polisen.se/api/events"
TRAFIKVERKET_API_URL = "https://api.trafikinfo.trafikverket.se/v2/data.json"

MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL")
TRAFIKVERKET_API_KEY = os.environ.get("TRAFIKVERKET_API_KEY")

# Bevakningsområde
TARGET_LOCATIONS = ["arvika", "eda", "årjäng", "värmland"]
TARGET_MUNICIPALITIES = ["Arvika", "Eda", "Årjäng"]

seen_police_ids = set()
seen_trafikverket_ids = set()

# --- HJÄLPFUNKTIONER ---
def matches_keyword(text):
    if not text:
        return False
    text_lower = text.lower()
    for kw in TARGET_LOCATIONS:
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            return True
    return False

# --- TRÅD 1: POLISENS API ---
def check_police_events():
    is_first_run = True

    while True:
        try:
            if not MAKE_WEBHOOK_URL:
                time.sleep(10)
                continue

            response = requests.get(POLISEN_API_URL, timeout=10)
            if response.status_code == 200:
                events = response.json()
                
                for event in events:
                    event_id = str(event.get("id"))
                    
                    if event_id in seen_police_ids:
                        continue
                    
                    if is_first_run:
                        seen_police_ids.add(event_id)
                        continue

                    name = event.get("name", "")
                    summary = event.get("summary", "")
                    location_name = event.get("location", {}).get("name", "")
                    
                    is_match = (
                        matches_keyword(name) or 
                        matches_keyword(summary) or 
                        matches_keyword(location_name)
                    )
                    
                    if is_match:
                        payload = {
                            "source": "Polisen",
                            "id": event_id,
                            "title": name,
                            "summary": summary,
                            "url": "https://polisen.se" + event.get("url", ""),
                            "type": event.get("type"),
                            "datetime": event.get("datetime"),
                            "location": location_name
                        }
                        requests.post(MAKE_WEBHOOK_URL, json=payload)
                    
                    seen_police_ids.add(event_id)
                
                is_first_run = False

                if len(seen_police_ids) > 2000:
                    ids_list = list(seen_police_ids)
                    seen_police_ids.clear()
                    seen_police_ids.update(ids_list[1000:])
                    
        except Exception as e:
            print(f"Fel vid polishämtning: {e}")
        
        time.sleep(30)

# --- TRÅD 2: TRAFIKVERKETS API ---
def check_trafikverket_events():
    is_first_run = True

    while True:
        try:
            if not MAKE_WEBHOOK_URL or not TRAFIKVERKET_API_KEY:
                time.sleep(10)
                continue

            # XML-fråga för att fånga olyckor/händelser i Värmlands län (CountyNo 17)
            xml_query = f"""
            <REQUEST>
              <LOGIN authenticationkey="{TRAFIKVERKET_API_KEY}" />
              <QUERY objecttype="Situation" schemaversion="1.2">
                <FILTER>
                  <ELEMENTMATCH>
                    <EQ name="Deviation.CountyNo" value="17" />
                  </ELEMENTMATCH>
                </FILTER>
                <INCLUDE>Id</INCLUDE>
                <INCLUDE>Deviation.Header</INCLUDE>
                <INCLUDE>Deviation.Details</INCLUDE>
                <INCLUDE>Deviation.CountyNo</INCLUDE>
                <INCLUDE>Deviation.IconId</INCLUDE>
                <INCLUDE>Deviation.StartTime</INCLUDE>
                <INCLUDE>Deviation.LocationDescriptor</INCLUDE>
                <INCLUDE>Deviation.MessageType</INCLUDE>
              </QUERY>
            </REQUEST>
            """

            headers = {'Content-Type': 'text/xml'}
            response = requests.post(TRAFIKVERKET_API_URL, data=xml_query, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                situations = data.get("RESPONSE", {}).get("RESULT", [{}])[0].get("Situation", [])

                for situation in situations:
                    sit_id = situation.get("Id")
                    deviations = situation.get("Deviation", [])

                    for dev in deviations:
                        event_id = f"tv_{sit_id}_{dev.get('MessageType', '')}"
                        
                        if event_id in seen_trafikverket_ids:
                            continue
                        
                        if is_first_run:
                            seen_trafikverket_ids.add(event_id)
                            continue

                        header = dev.get("Header", "")
                        details = dev.get("Details", "")
                        location = dev.get("LocationDescriptor", "")

                        # Matchar orter eller kommuner i ditt område
                        combined_text = f"{header} {details} {location}"
                        is_match = matches_keyword(combined_text)

                        if is_match:
                            payload = {
                                "source": "Trafikverket",
                                "id": event_id,
                                "title": f"Trafik: {header}",
                                "summary": details,
                                "url": "https://www.trafikverket.se",
                                "type": dev.get("MessageType", "Trafikhändelse"),
                                "datetime": dev.get("StartTime"),
                                "location": location
                            }
                            requests.post(MAKE_WEBHOOK_URL, json=payload)

                        seen_trafikverket_ids.add(event_id)

                is_first_run = False

                if len(seen_trafikverket_ids) > 2000:
                    ids_list = list(seen_trafikverket_ids)
                    seen_trafikverket_ids.clear()
                    seen_trafikverket_ids.update(ids_list[1000:])

        except Exception as e:
            print(f"Fel vid Trafikverkshämtning: {e}")

        time.sleep(60)  # Kollar Trafikverket en gång i minuten

# --- STARTA TRÅDAR ---
t1 = threading.Thread(target=check_police_events, daemon=True)
t2 = threading.Thread(target=check_trafikverket_events, daemon=True)

t1.start()
t2.start()
