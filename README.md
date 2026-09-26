# Courtyard

**Courtyard**  
Neighbors in a retirement community make everyday plans together. Private details stay off the board.

**Inspiration**

Retirement communities are full of people who want company, and short on easy ways to find it. A walk, lunch, cards, the library, a grocery trip, or a movie are small plans, and they fall through when the only way to arrange them is a bulletin board. Courtyard is for Sunrise Court, a fictional community, so residents can ask for company the way they already talk, and meet in shared places. A note that mentions a unit number, a door code, or living alone never becomes a card the building can see. Falls and medical distress go to the front desk, not to a neighbor.

**What it does**

Residents post a plan by typing or speaking. Courtyard turns that into a public card: a walk to lunch, cards, the garden, or a plan they write themselves, like a grocery carpool or golf. They can keep it to friends or open it to everyone. The feed shows the community, friends, or both. Friends are mutual, and the app suggests people you have already shared plans with.

Your events lists what you joined. The host can cancel, a guest can leave, and either can invite a friend. A bell collects those invites, joins, leaves, and cancellations.

Messages is a normal set of conversations. Tap a portrait and you are in that chat. Joining, leaving, or canceling a plan also lands in the thread. In a conversation, a sparkles button asks Grok for an idea based on both people’s tastes and the recent chat. The suggestion stays on screen until you tap Send or Not now. If you send it, the bubble is labeled Suggested by Grok.

Once a second person joins a plan, Grok writes a short spoken line, paints the meeting place, and records a voice clip. A speaker button plays that clip. Each resident has a painted portrait. The same board runs on the website and on a native iPhone app.

**How we built it**

A Python server is the source of truth. The website and a SwiftUI iPhone app are both clients of the same API.

Meta’s Model API runs on every note. Muse Spark classifies a known activity. Muse Voice Transcribe turns a spoken note into text. Contributor-tier models are not used.

xAI runs when people are actually together. Grok writes the spoken line and the message suggestion. Grok Imagine paints the rooms and the portraits. Grok Voice reads a grouped plan aloud. A suggestion is never posted until the resident sends it.

The safety fence runs before either API. The server removes unit numbers, door codes, medications, money, and “lives alone.” Public cards are a known activity, or a title taken locally after that cleanup. A line that still looks private is dropped. Emergency language goes to the front desk and is not turned into a plan or a message. Keys stay on the server.

**Challenges**

The models are good at repeating the note, which is exactly what could not be published. Place, time, and any sentence another resident can read are chosen or checked on our side, after private clauses are removed. A grocery trip or a golf outing still has to survive that check.

Voice on the phone took several passes: the silent switch, short recordings that came back empty, and plans that had no clip until a second person joined. The voice is generated once and then cached.

The phone also could not use the laptop’s own address on campus Wi-Fi, so the demo reaches the server through a tunnel.

**Accomplishments**

The same board runs on the web and on a physical iPhone, with portraits, place paintings, and a voice you can tap to hear. Friends, invites, and cancellations show up both as notices and as messages. Grok can propose a plan inside a conversation, and the resident decides whether it is sent. The public board can be full of ordinary days at Sunrise Court, and a unit number typed into a note still does not appear for anyone else.

**What we learned**

Bringing people together with a model is the easy half. Deciding what the model is never allowed to say out loud is the product. Classifying a walk is a small API call. Keeping a door code out of a chat, a painting prompt, and a spoken line is the part that has to win every time.

**What’s next**

A real front desk could confirm emergencies instead of a demo alert. Residents could set quiet hours, and plans could repeat on a weekday. Spoken notes already work on the web and should work in the iPhone composer too.
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
