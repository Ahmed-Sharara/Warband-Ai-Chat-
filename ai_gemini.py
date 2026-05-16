import time
import os
import requests
import json
import threading
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---
OPENROUTER_API_KEY = "YOUR-API-KEY"
MODEL_ID = "openai/gpt-oss-120b:free" 

WATCH_DIR = r"C:\Users\LOQ\Documents\Mount&Blade Warband WSE2\WSE\Native"
INPUT_FILE = os.path.abspath(os.path.join(WATCH_DIR, "To AI Chat.json"))
OUTPUT_FILE = os.path.abspath(os.path.join(WATCH_DIR, "From AI Chat.json"))

# --- GLOBAL STATE ---
session = requests.Session()
last_msg_hash = ""
last_processed_time = 0
COOLDOWN = 0.5 # Minimum seconds between API calls

def get_openrouter_response(text, name, kingdom, role):
    """Sends the request to OpenRouter using a persistent session."""
    if not OPENROUTER_API_KEY:
        print("!!! ERROR: OPENROUTER_API_KEY is missing.")
        return "I have no voice... (API Key Missing)"

    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # Context-aware instructions based on role
    village_context = " You are an elder responsible for your people's safety." if "elder" in name.lower() or "elder" in role.lower() else ""
    
    system_prompt = (
        f"Roleplay as {name}, a {role} of the {kingdom} in the world of Calradia.{village_context} "
        "Respond strictly in character with a gritty medieval tone. "
        "Your response MUST be ONLY the spoken dialogue. Max 15 words. "
        "IMPORTANT: If the player explicitly threatens to KILL you, ATTACK your village, or BURN property, "
        "and you are in a position where this would provoke a fight, "
        "append the exact text [ACTION_HOSTILE] to the end of your response."
    )
    
    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"The player says: '{text}'"}
        ],
        "temperature": 0.6,
        "max_tokens": 45
    }
    
    try:
        r = session.post(url, headers=headers, json=payload, timeout=12)
        
        if r.status_code == 200:
            result = r.json()
            try:
                # OpenRouter format extraction
                text_response = result['choices'][0]['message']['content']
                return text_response
            except KeyError:
                print("!!! API Format Error. Raw response:", result)
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

            print(f"\n[EVENT] Processing message from {data.get('name')} ({data.get('role', 'NPC')}): {msg}")

            # 5. Clear Input Immediately (Prevent ghost loops)
            with open(INPUT_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

            # 6. Get AI Response via OpenRouter
            role = data.get("role", "commoner").lower()
            response_text = get_openrouter_response(msg, data.get("name", "Lord"), data.get("kingdom", "Calradia"), role)
            
            # 7. Format for Warband (Remove JSON-breaking characters)
            clean_response = response_text.replace("\n", " ").replace('"', "'").strip()

            out_data = {"response": clean_response}

            # --- ROLE-BASED ACTION OVERRIDE (CRITICAL SECURITY) ---
            # We only allow direct combat jumps for Village Elders to prevent bugs with Kings/Lords
            is_threat = any(word in msg.lower() for word in ["burn", "killing", "raid", "destroy", "attack", "to arms"])
            is_elder = "elder" in data.get("name", "").lower() or "elder" in role
            
            if "[ACTION_HOSTILE]" in clean_response:
                # 1. Always remove the technical tag from the spoken dialogue
                clean_response = clean_response.replace("[ACTION_HOSTILE]", "").strip()
                out_data["response"] = clean_response

                # 2. Hard Enforcement: ONLY Village Elders responding to a threat can trigger 'hostile'
                if is_elder and is_threat:
                    out_data["action"] = "hostile"
                    print(f"[DEBUG] HOSTILE action approved for Village Elder.")
                else:
                    # If it's a King, Lord, or anyone NOT an elder, we FORCE it to be peaceful 
                    # even if the player was rude, to avoid breaking game balance/logic.
                    print(f"[DEBUG] REJECTED HOSTILE action. NPC is not an Elder or input wasn't a threat. Role: {role}")
            
            # Additional safety: If user didn't mention burning/killing, strip the hostile action anyway
            elif not is_threat and out_data.get("action") == "hostile":
                del out_data["action"]

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
