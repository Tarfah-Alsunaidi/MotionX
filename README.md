# MotionX · 🌪️ Storm City

A full-screen, street-level interactive story built on the notebook
*Dimensionality Reduction Mini Project: Human Activity Recognition*.
Players join from their phones as new residents of Sensor City, appear as their own characters, and live through the storm.

## Run it

**Recommended: Streamlit Community Cloud.** Players can join from any internet (mobile data, any Wi-Fi).
See `خطوات_الرفع.md` for the step-by-step guide. On the first start the app downloads the dataset
from UCI and prepares the UMAP lens by itself.

**Or from your laptop** (players must be on the same Wi-Fi):
```bash
pip install -r requirements.txt
python precompute.py                                  # optional: UMAP lens ahead of time
streamlit run app.py --server.address 0.0.0.0
```

1. Open the app on the projector. This is the big screen.
2. Players scan the QR code in the corner of the big screen. It opens `/?join=1`.
3. Each player types their name, picks a look (thobe, abaya or casual; shmagh, hijab, hair or cap; colours),
   and picks a **place**, which is their activity in the dataset:

   | Place (always written in Arabic) | Activity |
   |---|---|
   | ☕ MotionX coffee (café) | sitting |
   | 🛒 طابور سوق النجوم (market queue) | standing |
   | 🌿 حديقة الحي (park lawn) | lying down |
   | 🚶 الممشى (walkway) | walking |
   | ⬆️ / ⬇️ درج المجمع (mall stairs) | going upstairs / downstairs |

   Their phone carries a **real moment from the dataset** for that activity.
4. Players appear on the big screen with a ⭐ name tag and live in the city.

**Languages:** Arabic first. A small **EN / ع** button on the side of the big screen switches the story to English;
the phone has its own small switch. Place names, signs and ads stay in Arabic in both languages.

The presenter tools (remove everyone, fix the join link) are under **⚙️ Presenter settings** below the game,
behind a PIN: `561` by default, change it with `PRESENTER_PIN` in Streamlit secrets.

## The phone (`/?join=1`)

`web/phone.html` is a game-styled screen (a Streamlit component):
1. **Name** → 2. **Look** (thobe / abaya / casual, head, colours, with a live avatar) → 3. **Place** (= activity) → **Enter the city**.
Then the same screen follows the story: shake + vibration in the storm, **Fix my look / Stay messy** after it,
a scanning animation in the store, the result with **Yes / No**, and goodbye at the end.
Everything the phone sends is checked on the server (only the offered colours/styles, cleaned names), and the
player's id is kept in the link (`&me=…`) so a refresh keeps the same character.

## The story

A Saudi festival night on the boulevard (fictional "موسم الحساسات"): Najdi mud houses, LED screens, palms,
string lights, fireworks, a glass café, a rock-arch store. All brands and ads are fictional.

1. **A tour of the city:** the camera walks like a person (smooth speed, head bob, steps around planters,
   the LED pillar, the dome and people). Townsfolk walk, window-shop and sit having coffee in the glass café.
2. **New residents arrive:** players scan the QR code and join.
3. **The storm:** wind, rain, thunder, soft screams; people and palm trees shake; the big screen shakes and
   phones vibrate (Android) or shake on screen (iPhone). Every activity blows away.
4. **After the storm:** everyone is on the ground with dizzy heads; people get up and help each other up.
   "What happened? What were we doing?" Then a **police car** and the **Statistics Center** van arrive.
   The statistician explains that the phones still hold their 561 numbers, and everyone walks to the
   MotionX market. Players can **fix their look** or **stay messy** on their phone.
5. **Inside the store:** a real shop with a clerk, a scanner gate and a big screen. The presenter picks the model,
   exactly the notebook's pipeline:
   - `StandardScaler`, then all 561 / PCA 95% / PCA 2 / UMAP 10
   - then K-Means (k=6) or DBSCAN (eps 14 on 561, 1.0 on PCA 2)
   - each group is named after its most common activity (the notebook's `name_clusters`)

   Everyone walks through the scanner one by one while the Statistics officer watches; faces appear on the
   big screen. Then the officer explains the result with the notebook's **ARI** and **Silhouette** (on the 561
   features, sample of 3000) and the faces are grouped by the model's answer.
6. **The result:** each phone says "you were sitting at MotionX coffee — is that right?". ✅ makes the face happy
   and the person leaves the store; ❌ makes it sad.
7. **Back to our places:** everyone walks out to their place; green ring = the model was right, red = wrong.
8. **Farewell picnic:** everyone sits on sadu rugs in the park with kabsa, dates and Saudi coffee, laughs,
   fireworks, then waves goodbye. **📋 What did we learn?** shows every model's ARI and Silhouette and the lessons.

**MotionX additions:** friendly characters (big round heads, clear faces, slim, all the same size), few labels on screen,
realistic shops with fictional names (dates & maamoul, cakes, sushi, burgers, Najdi-style pizza, a music store, a clothing store),
MotionX coffee and MotionX market, an ambulance with a paramedic, a sandstorm with rain that dirties the camera lens,
and a campfire finale with s'mores, food, coffee, matcha and an outdoor projector screen.

**Music store:** walking past it plays original built-in tunes at random. To play your own songs, put files you have the
right to use (.mp3/.m4a/.ogg) in `web/music/`. Note: if the GitHub repo is public, anyone can download them.

**Sound:** everything is generated in the browser: music that changes with each scene, birds, café murmur,
wind, rain, thunder, soft screams, groans, laughter, cheers, a siren, the scanner, fireworks. Characters
"speak" in game-style voices (each person keeps their own voice and tone: dizzy, scared, firm, happy) while
their words appear in bubbles. Use 🔊 to mute.

## Files

| File | What it does |
|---|---|
| `app.py` | The big screen (the game as a live component) and the phone page (`/?join=1`). |
| `core/city.py` | The notebook's pipeline, plus the game data (pure Python). |
| `core/classroom.py` | The shared room: players, looks, places, answers, story act. |
| `core/data.py` | Loads `har.csv`, then scaling and PCA. |
| `web/city.html` | The game: boulevard, storm, aftermath, store scan, picnic, sound and the AR/EN switch. |
| `web/bridge.js` | Lets the game talk to Streamlit without reloading. |
| `precompute.py` | Computes the UMAP lens once. |
