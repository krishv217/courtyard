# Courtyard

Daily company for Sunrise Court, a retirement community. Residents ask for a walk, lunch, cards, the library, or the garden. Plans meet in shared rooms. Unit numbers, door codes, and being alone never go on the board.

## Run

```bash
cp .env.example .env
python3 server.py
```

Open http://127.0.0.1:8787

The app runs without keys. Add keys to `.env` and restart the server:

- `XAI_API_KEY` from https://console.x.ai — Grok writes the spoken plan, Grok Imagine paints the room, Grok Voice reads it aloud.
- `MODEL_API_KEY` from the Meta Model API dashboard — Muse Spark classifies the activity, Muse Voice Transcribe hears hold-to-talk notes.

Both keys stay on the server. Use fictional notes in the demo. Meta's discounted contributor models are not used, because those can train on prompts.
