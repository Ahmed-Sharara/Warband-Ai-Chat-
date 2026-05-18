import time
import os
import requests
import json
import hashlib
import threading
import webbrowser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# =============================================================================
# PLAYER2 BRIDGE FOR WARBAND AI CHAT
# =============================================================================
# Choose your mode:
#   "app"    - Connects to the Player2 App running on your PC (no key needed)
#   "apikey" - Uses your Player2 API key. If you leave PLAYER2_API_KEY empty,
#              a browser window will open so you can generate one automatically.
# =============================================================================

MODE = "app"  # "app" or "apikey"

# Only needed if MODE = "apikey". Leave empty to generate one via browser.
PLAYER2_API_KEY = ""

# Set this to the folder where you installed the mod files.
# Example: r"C:\Users\YourName\OneDrive\Documents\Mount&Blade Warband WSE2\WSE\Native"
# Example: r"C:\Users\YourName\Documents\Mount&Blade Warband WSE2\WSE\Native"
WATCH_DIR = r"C:\Users\YourUser\Documents\Mount&Blade Warband WSE2\WSE\Native"

# --- Don't touch these ---
GAME_CLIENT_ID  = "019e3c62-2a9e-7de3-a7ea-9222669593f4"
P2_API_BASE     = "https://api.player2.game/v1"
P2_CHAT_URL     = f"{P2_API_BASE}/chat/completions"
P2_HEALTH_URL   = f"{P2_API_BASE}/health"
P2_APP_LOGIN    = f"http://localhost:4315/v1/login/web/{GAME_CLIENT_ID}"
P2_DEVICE_NEW   = f"{P2_API_BASE}/login/device/new"
P2_DEVICE_TOKEN = f"{P2_API_BASE}/login/device/token"
INPUT_FILE      = os.path.abspath(os.path.join(WATCH_DIR, "To AI Chat.json"))
OUTPUT_FILE     = os.path.abspath(os.path.join(WATCH_DIR, "From AI Chat.json"))
KEY_FILE        = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".p2key")
COOLDOWN        = 0.5

session             = requests.Session()
p2_key              = ""
last_msg_hash       = ""
last_processed_time = 0
memory_db           = {}  # Stores 1 previous conversation per NPC


# --- Key persistence ---

def save_key(key):
    with open(KEY_FILE, "w") as f:
        f.write(key)

def load_saved_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r") as f:
            return f.read().strip()
    return ""

def clear_saved_key():
    if os.path.exists(KEY_FILE):
        os.remove(KEY_FILE)

def verify_key(key):
    try:
        r = requests.get(P2_HEALTH_URL, headers={"Authorization": f"Bearer {key}"}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# --- OAuth Device Code flow ---

def oauth_login():
    """Opens the browser for the user to log in and returns a p2Key."""
    print("[AUTH] Opening Player2 login in your browser ...")
    try:
        r = requests.post(P2_DEVICE_NEW, json={"client_id": GAME_CLIENT_ID}, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[AUTH] ERROR starting login flow: {e}")
        input("Press Enter to exit...")
        raise SystemExit(1)

    interval     = data.get("interval", 5)
    device_code  = data.get("deviceCode")
    complete_url = data.get("verificationUriComplete") or data.get("verificationUri")
    user_code    = data.get("userCode")

    webbrowser.open(complete_url)
    if user_code:
        print(f"[AUTH] If the browser didn't open, go to: {complete_url}")
        print(f"[AUTH] And enter code: {user_code}")

    print("[AUTH] Waiting for approval", end="", flush=True)
    while True:
        time.sleep(interval)
        print(".", end="", flush=True)
        try:
            poll = requests.post(P2_DEVICE_TOKEN, json={
                "client_id":   GAME_CLIENT_ID,
                "device_code": device_code,
                "grant_type":  "urn:ietf:params:oauth:grant-type:device_code"
            }, timeout=10)
            key = poll.json().get("p2Key")
            if key:
                print("\n[AUTH] Login approved!")
                return key
        except Exception:
            pass


# --- Auth ---

def authenticate():
    global p2_key

    if MODE == "app":
        print("[AUTH] Connecting to Player2 App on localhost:4315 ...")
        try:
            r = requests.post(P2_APP_LOGIN, timeout=5)
            r.raise_for_status()
            p2_key = r.json().get("p2Key", "")
            if not p2_key:
                print("[AUTH] ERROR: Player2 App returned no key. Are you logged in?")
                input("Press Enter to exit...")
                raise SystemExit(1)
            print("[AUTH] Got key from Player2 App.")
        except requests.exceptions.ConnectionError:
            print("[AUTH] ERROR: Could not reach Player2 App.")
            print("       Make sure the Player2 App is running and you are logged in.")
            input("Press Enter to exit...")
            raise SystemExit(1)

    elif MODE == "apikey":
        if PLAYER2_API_KEY:
            p2_key = PLAYER2_API_KEY
            print("[AUTH] Using API key from config.")
        else:
            saved = load_saved_key()
            if saved:
                print("[AUTH] Found saved key, verifying ...")
                if verify_key(saved):
                    p2_key = saved
                    print("[AUTH] Saved key is valid.")
                    return
                else:
                    print("[AUTH] Saved key expired, generating a new one ...")
                    clear_saved_key()

            p2_key = oauth_login()
            save_key(p2_key)
            print("[AUTH] Key saved. You won't need to log in again next time.")

    else:
        print(f"!!! ERROR: Unknown MODE '{MODE}'. Use 'app' or 'apikey'.")
        input("Press Enter to exit...")
        raise SystemExit(1)


def health_ping():
    """Player2 requires a health check every 60s to track game usage."""
    def loop():
        while True:
            time.sleep(60)
            try:
                session.get(P2_HEALTH_URL, headers={"Authorization": f"Bearer {p2_key}"}, timeout=5)
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()


def get_player2_response(text, data):
    global memory_db

    name     = data.get("name", "Lord")
    kingdom  = data.get("kingdom", "Calradia")
    role     = data.get("role", "commoner").lower()
    relation = data.get("relation", 0)
    location = data.get("location", "Unknown Location")
    king     = data.get("king", "None")

    # Role-specific context
    if "elder" in role:
        role_context = f" You are the elder of {location}. You report to the lords of {kingdom}."
    elif "king" in role:
        role_context = f" You are the ruler of {kingdom}! You demand absolute respect. You are currently at {location}."
    elif "lord" in role:
        king_str = f" You are a vassal of {king}." if king and king != "None" else ""
        role_context = f" You are a proud noble of {kingdom}.{king_str} You are currently at {location}."
    else:
        role_context = f" You are currently at {location}."

    # Relation context
    relation_str = "You are neutral to the player."
    try:
        rel_int = int(relation)
        if rel_int < -10:
            relation_str = "You HATE the player."
        elif rel_int < 0:
            relation_str = "You dislike the player."
        elif rel_int > 20:
            relation_str = "You are good friends with the player."
        elif rel_int > 5:
            relation_str = "You like the player."
    except Exception:
        pass

    # Memory
    memory_key      = f"{name}_{kingdom}"
    previous_convo  = memory_db.get(memory_key)
    memory_str      = ""
    if previous_convo:
        memory_str = (
            f"PREVIOUS CONVERSATION (Memory):\n"
            f"Player said: '{previous_convo['player']}'\n"
            f"You said: '{previous_convo['npc']}'\n\n"
        )

    system_prompt = (
        f"Roleplay as {name}, a {role} of the {kingdom} in the world of Calradia.{role_context} {relation_str} "
        "Respond strictly in character with a gritty medieval tone. "
        "Your response MUST be ONLY the spoken dialogue. Max 15 words. "
        "IMPORTANT: If the player explicitly threatens to KILL you, ATTACK your village, or BURN property, "
        "and you are in a position where this would provoke a fight, "
        "append the exact text [ACTION_HOSTILE] to the end of your response.\n\n"
        f"{memory_str}"
    )

    payload = {
        "messages": [
            {"content": system_prompt,                "role": "system"},
            {"content": f"The player says: '{text}'", "role": "user"}
        ],
        "temperature": 0.6,
        "max_tokens": 45
    }

    headers = {
        "Authorization": f"Bearer {p2_key}",
        "Content-Type": "application/json"
    }

    try:
        r = session.post(P2_CHAT_URL, headers=headers, json=payload, timeout=12)
        if r.status_code == 200:
            result = r.json()
            try:
                text_response = result["choices"][0]["message"]["content"]
                memory_db[memory_key] = {"player": text, "npc": text_response}
                return text_response
            except (KeyError, IndexError, TypeError):
                print("!!! API format error.")
                return "The winds carry foul words. I will not answer."
        elif r.status_code == 401:
            print("!!! AUTH ERROR: Key expired. Restart the bridge to log in again.")
            clear_saved_key()
            return "My tongue is bound by dark magic... (Auth Error)"
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
        if os.path.abspath(event.src_path) == INPUT_FILE:
            self.process_request()

    def on_created(self, event):
        if os.path.abspath(event.src_path) == INPUT_FILE:
            self.process_request()

    def process_request(self):
        global last_msg_hash, last_processed_time

        try:
            current_time = time.time()
            if (current_time - last_processed_time) < COOLDOWN:
                return

            time.sleep(0.05)
            if not os.path.exists(INPUT_FILE) or os.stat(INPUT_FILE).st_size < 5:
                return

            with open(INPUT_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    return

            msg = data.get("message", "").strip()
            if not msg:
                return

            current_hash = hashlib.md5(msg.encode("utf-8")).hexdigest()
            if current_hash == last_msg_hash:
                return
            last_msg_hash       = current_hash
            last_processed_time = current_time

            print(f"\n[EVENT] Processing message from {data.get('name')} ({data.get('role', 'NPC')}): {msg}")

            with open(INPUT_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

            response_text = get_player2_response(msg, data)

            clean_response = response_text.replace("\n", " ").replace('"', "'").strip()
            out_data = {"response": clean_response}

            is_threat = any(word in msg.lower() for word in ["burn", "killing", "raid", "destroy", "attack", "to arms"])
            is_elder  = "elder" in data.get("name", "").lower() or "elder" in data.get("role", "").lower()

            if "[ACTION_HOSTILE]" in clean_response:
                clean_response = clean_response.replace("[ACTION_HOSTILE]", "").strip()
                out_data["response"] = clean_response
                if is_elder and is_threat:
                    out_data["action"] = "hostile"
                    print(f"[DEBUG] HOSTILE action approved for Village Elder.")
                else:
                    print(f"[DEBUG] REJECTED HOSTILE action. NPC is not an Elder or input wasn't a threat. Role: {data.get('role', '')}")
            elif not is_threat and out_data.get("action") == "hostile":
                del out_data["action"]

            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(out_data, f, ensure_ascii=False)

            print(f"[SUCCESS] AI Answered: {clean_response}")

        except Exception as e:
            print(f"!!! Processing Error: {e}")


if __name__ == "__main__":
    print(f"--- CALRADIA AI BRIDGE - Powered by Player2 (Mode: {MODE.upper()}) ---")
    print(f"Watching: {WATCH_DIR}")

    authenticate()
    health_ping()

    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

    event_handler = AIBridgeHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()

    print("[READY] Bridge is running. Launch Warband and start chatting.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()