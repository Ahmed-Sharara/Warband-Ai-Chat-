import time
import os
import requests
import json
import threading
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---
# REPLACE WITH YOUR NEW API KEY (The old one is compromised!)
API_KEY = "YOUR_API_KEY"

MODEL_ID = "gemini-3.1-flash-lite" # Or any model you want

WATCH_DIR = r"C:\Users\LOQ\Documents\Mount&Blade Warband WSE2\WSE\Native"
INPUT_FILE = os.path.abspath(os.path.join(WATCH_DIR, "To AI Chat.json"))
OUTPUT_FILE = os.path.abspath(os.path.join(WATCH_DIR, "From AI Chat.json"))

# --- GLOBAL STATE ---
session = requests.Session()
last_msg_hash = ""
last_processed_time = 0
COOLDOWN = 0.5 # Minimum seconds between API calls

def get_gemini_response(text, name, kingdom):
    """Sends the request to Gemini using a persistent session."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"
    
    prompt = (
        f"Roleplay as {name}, a character of the {kingdom} in the world of Calradia. "
        f"The player says: '{text}'. "
        "Respond strictly in character with a gritty medieval tone. "
        "Your response MUST be ONLY the spoken dialogue. Max 15 words. "
        "IMPORTANT: If the player threatens to kill you, attack you, or burn your property/village, you MUST append the exact text [ACTION_HOSTILE] to the end of your response."
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 45
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    
    try:
        # Using session.post instead of requests.post saves ~200-400ms per call
        r = session.post(url, json=payload, timeout=12)
        
        if r.status_code == 200:
            result = r.json()
            try:
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                return text_response
            except KeyError:
                print("!!! API Safety/Format Error. Raw response:", result)
                return "The winds carry foul words. I will not answer."
        elif r.status_code == 429:
            print("!!! RATE LIMIT REACHED: Slow down the conversation.")
            return "My mind is clouded with exhaustion... (Rate Limit)"
        else:
            print(f"!!! API Error {r.status_code}: {r.text}")
            return "I have no words for you."
    except Exception as e:
        print(f"!!! Connection Error: {e}")
        return "The winds are too loud for us to speak."

class AIBridgeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        # Only trigger if the input file was changed
        if os.path.abspath(event.src_path) == INPUT_FILE:
            self.process_request()

    def process_request(self):
        global last_msg_hash, last_processed_time
        
        try:
            # 1. Immediate Cooldown (Debounce)
            current_time = time.time()
            if (current_time - last_processed_time) < COOLDOWN:
                return
            
            # 2. File Lock Safety
            time.sleep(0.05) 
            if not os.path.exists(INPUT_FILE) or os.stat(INPUT_FILE).st_size < 5:
                return

            # 3. Read Data
            with open(INPUT_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    return

            msg = data.get("message", "").strip()
            if not msg:
                return

            # 4. Content Hashing (Stop duplicate calls for the same message)
            current_hash = hashlib.md5(msg.encode('utf-8')).hexdigest()
            if current_hash == last_msg_hash:
                return
            
            last_msg_hash = current_hash
            last_processed_time = current_time

            print(f"\n[EVENT] Processing message from {data.get('name')}: {msg}")

            # 5. Clear Input Immediately (Prevent ghost loops)
            with open(INPUT_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

            # 6. Get AI Response
            response_text = get_gemini_response(msg, data.get("name", "Lord"), data.get("kingdom", "Calradia"))
            
            # 7. Format for Warband (Remove JSON-breaking characters)
            clean_response = response_text.replace("\n", " ").replace('"', "'").strip()

            out_data = {"response": clean_response}
            if "[ACTION_HOSTILE]" in clean_response:
                clean_response = clean_response.replace("[ACTION_HOSTILE]", "").strip()
                out_data["response"] = clean_response
                out_data["action"] = "hostile"

            # 8. Write to Game
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(out_data, f, ensure_ascii=False)
            
            print(f"[SUCCESS] AI Answered: {clean_response}")


        except Exception as e:
            print(f"!!! processing Error: {e}")

if __name__ == "__main__":
    print(f"--- CALRADIA AI BRIDGE (Model: {MODEL_ID}) ---")
    print(f"Watching: {WATCH_DIR}")

    # Clean start
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "w", encoding="utf-8") as f: json.dump({}, f)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: json.dump({}, f)

    event_handler = AIBridgeHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
