# Warband AI NPCs & Village Engagement Mod

This project connects Mount & Blade: Warband to AI language models. Instead of reading the exact same dialogue lines over and over, you can actually type to NPCs and get dynamic responses based on their character, faction, and role. 

This isn't just text, either. The mod hooks into the game's actual mechanics. For example, if you threaten to burn a village or kill the inhabitants while talking to a Village Elder, the AI detects the threat, the script validates the NPC's role, and the game throws you straight into the battle/raid menu. 

I've provided three different Python scripts to run the bridge. You can run the AI locally on your own PC, use a cloud API for heavier models, or connect through Player2 for a free, account-based option.

## How the bridge works

The game engine can't talk to AI models directly, so we use a fast file-reading trick. When you type a message to an NPC, the game's module scripts save your message, the NPC's name, their role, and their faction into a file called `To AI Chat.json`.

One of the Python scripts runs in the background and constantly watches that file. The moment you hit enter in-game, the script grabs the text, feeds it to the AI, cleans up any weird formatting from the response, and writes it to `From AI Chat.json`. The game instantly reads it back and makes the NPC speak.

The python script also handles the logic for hostile actions. It specifically checks if you are talking to a Village Elder before allowing a village raid to trigger. If you try to threaten a King or a Lord with village raid dialogue, the script intercepts the hostile tag so you don't break the game state.

## Installation

You need Python 3 installed on your machine.
Open your command prompt and install the dependencies:

```bash
pip install requests watchdog
```

## Running the AI

You have three options depending on your setup. Make sure the `WATCH_DIR` variable in your chosen script points to the folder where you installed the mod files. For example:

```
C:\Users\YourName\Documents\Mount&Blade Warband WSE2\WSE\Native
```

### Option 1: Local Bridge (ai_bridge_local.py)
Use this if you want to run a model locally on your own hardware using LM Studio. It's fully offline and great if you have the RAM for it.
1. Download LM Studio and load up a fast model.
2. Start the Local Server in LM Studio on port 1234.
3. Run `python ai_bridge_local.py` in your terminal.
4. Launch Warband.

### Option 2: Cloud Bridge (ai_bridge_cloud.py)
Use this if you want to connect to a cloud provider like OpenRouter to access massive models that you couldn't run locally. 
1. Open up `ai_bridge_cloud.py` in a text editor.
2. Paste your API key into the `OPENROUTER_API_KEY` variable.
3. Run `python ai_bridge_cloud.py` in your terminal.
4. Launch Warband.

### Option 3: Player2 Bridge (ai_bridge_player2.py)
Use this to connect through [Player2](https://player2.game), a free gaming AI platform. No need to manage API keys or run anything locally.

Open `ai_bridge_player2.py` and set your mode at the top of the file:

```python
MODE = "app"  # "app" or "apikey"
```

**App mode** requires the Player2 desktop app running on your PC. It handles authentication automatically with no extra steps.

**API key mode** uses a Player2 API key. If you leave `PLAYER2_API_KEY` empty, a browser window will open the first time so you can log in and generate one automatically. The key gets saved locally so you won't need to log in again.

Then:
1. Run `python ai_bridge_player2.py` in your terminal.
2. Approve the login in your browser if prompted (first time only).
3. Launch Warband.

## Compiling the Mod Files

If you want to tweak the game logic or rebuild the module:
1. Drop the `module_*.py` files into your Warband Module System folder.
2. Run your `build_module.bat` to compile the changes into text files for the game engine.
3. Start the Python bridge, load up the game, and go talk to an NPC.