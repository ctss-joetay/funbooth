# 📸 Fun Booth

An AI photo booth that runs in the browser on iPads, iPhones and laptops. Guests swipe
through themes with sample pictures, pick one and strike a pose. The AI (ByteDance
**Seedream 5.0 Flash** via OpenRouter) restyles them into the theme. Only the operator
can print the photo or send it to guests.

**Themes included:** Winter Wonderland · Holidays in the Sun · Music Festival ·
Lunar New Year · Festival of Lights · Christmas Cheer · Totally 80s · 90s Throwback ·
Y2K 2000s · Red Carpet · Custom (operator types any scene)

## Pick a setup

| Setup | Guest screen (`/display`) | Camera | Print & send |
|---|---|---|---|
| **One iPad does everything** | the iPad (choose “Camera + guest screen”) | the same iPad's front camera | PIN-protected host menu on the iPad (⚙︎ corner) |
| **Operator iPad is the camera** | second iPad (“Guest screen only”) | operator iPad (`/operator`) | operator iPad |
| **Phone as the camera** | iPad (“Guest screen only”) | iPhone or any device (`/camera`) | operator iPad or laptop (`/operator`) |
| **Laptop operator** | iPad (“Guest screen only”) | laptop webcam, or a phone on `/camera` | laptop, which can print to any installed printer |

Choose the camera in the operator's **Settings → Which device takes the photo?**
(This device / Guest iPad / Phone or other). The camera page and the guest screen's
start screen can also set it. When the camera is on another device, it streams a live
preview to the guest screen (about 6 low-res frames a second through the server), so
guests still see themselves while posing.

```
   Guest screen (iPad)               Camera (any one)             Operator (iPad or laptop)
 ┌─────────────────────┐   live    ┌──────────────────┐         ┌──────────────────────────┐
 │ swipe themes        │◄──preview─│ operator device  │         │ themes · take photo      │
 │ tap "Take my photo" │           │ or iPhone /camera│         │ restyle · print · send   │
 │ countdown · result  │           │ or the guest iPad│         │ gallery · samples        │
 └─────────┬───────────┘           └────────┬─────────┘         └────────────┬─────────────┘
           └────────────────── Railway (FastAPI + WebSockets) ───────────────┘
                                          │
                              OpenRouter → Seedream 5.0 Flash
```

## How a photo is taken

1. **Choose:** guests swipe the theme carousel on the guest screen and tap a theme.
   The operator decides which themes appear and can add sample pictures (see below).
2. **Pose:** the guest screen shows the live camera. A guest taps **Take my photo!**,
   or the operator taps **Take photo**, or the photographer presses the phone's shutter.
3. **Countdown:** 3-2-1 and a flash on every screen. The camera device captures the
   frame, cropped to exactly what was on screen.
4. **AI:** the photo and theme prompt go to Seedream. Every prompt starts with an
   instruction to keep faces, poses and the number of people unchanged.
5. **Result:** the guest screen shows the photo and tells guests to ask the host for a
   print or copy. Guests can take another photo or pick a new theme. The screen goes
   back to the themes after two minutes on its own.
6. **Operator only:**
   - **Print:** opens a preview of a framed 6×4" (or 4×6") card at 300 dpi with the
     event name, date and an optional QR code.
   - **Send:** shows a QR code guests scan from the operator screen, AirDrop where the
     browser supports it, **Show QR on guest screen**, or downloads (handy on a laptop).
   - **Restyle:** re-runs the selected photo with another theme.

## Theme samples

The carousel shows an illustrated card for each theme until it has a sample picture.
To add samples:
- **⭐ Use as theme sample:** on any finished photo in the operator view.
- **Settings → Make samples for every theme from the selected photo:** restyles one
  good shot (e.g. your team) in every theme. This is one AI image per theme, ~10 in total.
- **Built-in defaults:** add `static/samples/<theme id>.jpg` files to the repo, e.g.
  `static/samples/winter.jpg`. Samples made in the app take priority.

## Run it locally (no API key needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
BOOTH_PIN=2468 uvicorn app.main:create_app --factory --reload
```

Open http://localhost:8000. Without `OPENROUTER_API_KEY` the app runs in **mock
mode**: the "AI" just tints the photo, so you can rehearse the whole flow for free.
Run the tests with `pytest`.

> The camera only works on `localhost` or over HTTPS. To test with real iPads, deploy
> to Railway (HTTPS is automatic) or use a tunnel.

## Deploy to Railway

1. Push this folder to a GitHub repo.
2. In Railway, create a **New Project → Deploy from GitHub repo** and pick the repo.
   The included `Dockerfile` and `railway.json` are picked up automatically.
3. Under **Variables**, add at least:
   - `OPENROUTER_API_KEY`: your key from https://openrouter.ai/keys
   - `BOOTH_PIN`: the PIN both iPads will use
   - `EVENT_NAME`: printed on every photo (you can also change it in the app)
   - `TIMEZONE`: e.g. `Asia/Singapore`, used for the printed date
4. Add a **Volume** to the service mounted at **`/data`**. Photos and settings are
   kept there; without it they are lost on every redeploy.
5. Under **Settings → Networking**, click **Generate Domain**. You'll get
   `https://<something>.up.railway.app`.
6. Open the operator iPad's **Settings → Test AI connection** to confirm the key
   and model work. This makes one real image, which costs a few cents.

Keep the service at **one replica**: the live booth state is held in memory.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | *(empty → mock mode)* | OpenRouter key |
| `BOOTH_PIN` | random, printed in logs | PIN that unlocks every device and the host menu |
| `EVENT_NAME` | `Fun Booth` | Initial event name (editable in the app) |
| `OPENROUTER_MODEL` | `bytedance-seed/seedream-5-0-flash` | Any OpenRouter image model that accepts an input image |
| `OPENROUTER_API_MODE` | `auto` | `images` (unified `/images` API), `chat` (`/chat/completions` with image output), or `auto` (try `/images`, fall back to chat) |
| `OPENROUTER_RESOLUTION` | `2K` | `1K` is cheaper and faster; `2K` prints sharper. Empty uses the model default |
| `OPENROUTER_TIMEOUT` | `120` | Seconds to wait for the AI |
| `TIMEZONE` | `UTC` | Time zone for the date on prints |
| `DATA_DIR` | `/data` in Docker | Where photos are stored (mount a volume here) |
| `PUBLIC_URL` | Railway domain | Override the URL used in QR codes, e.g. for a custom domain |

## Setting up the devices

**Guest screen** (the iPad facing the guests)
1. In Safari open `https://<your-app>/display`, enter the PIN, then choose
   **Camera + guest screen** or **Guest screen only**.
2. For a full-screen kiosk, tap Share → **Add to Home Screen** and launch it from there.
3. Set Settings → Display & Brightness → **Auto-Lock → Never**, and turn on
   **Guided Access** (Settings → Accessibility) so guests can't leave the app.
4. The faint ⚙︎ in the top-right corner asks for the PIN, then opens the **host menu**:
   - print, AirDrop or show a QR code for any recent photo
   - choose whether this iPad is the camera, and front or back camera
   - links to full screen and the operator controls

**Operator** (iPad or laptop): open `https://<your-app>/operator`.
- Check that the status chips show **Server**, **Guest screen** and the camera in green.
- ⚙️ Settings covers:
  - event name and print layout
  - which device takes the photo, and the countdown length
  - which themes guests can choose
  - theme samples
  - uploading a photo instead of using the camera
  - testing the AI connection
- On a laptop, the keyboard shortcuts are **Space** take photo, **P** print, **S** send,
  **N** next guest.

**Camera** (optional iPhone or other device): open `https://<your-app>/camera` and tap
**Start camera**. It becomes the booth camera (untick the box to keep it on standby).
Hold it sideways for landscape prints. Use 🔄 to switch between front and back camera,
and the round button is the shutter.

All devices only need internet access; they don't have to be on the same Wi-Fi.

## Printing

Printing is done by the operator (or the host menu on a one-iPad booth): **Print →
preview → Print → choose printer**. On an iPad that's **AirPrint**. On a laptop any
installed printer works, including USB event printers such as DNP or Mitsubishi. In the print options pick **4×6 / 10×15 cm** paper and the number of
copies. Any AirPrint photo printer works. Canon SELPHY dye-sub printers are a popular
choice for booths; check that the model you buy lists AirPrint. Printers without
AirPrint, such as many DNP/Mitsubishi event printers, need a print server or the
maker's iPad app.

## Sending photos: AirDrop, QR and Bluetooth

Guests can't print or download from the guest screen by themselves. The operator sends
each photo:
- **QR code:** shown in the operator's Send dialog for the guest to scan, or pushed
  to the guest screen with **Show QR on guest screen**. Any phone works, Android
  included.
- **AirDrop:** from an iPad or Safari on a Mac, the share sheet sends the framed and
  plain photos. AirDrop uses Bluetooth plus Wi-Fi.
- **Downloads:** saves the plain or framed version, e.g. to email or upload later.
- **QR code on prints** (optional): printed photos carry a QR code to the digital copy.

The browser can't talk to Bluetooth devices directly (iOS doesn't support Web
Bluetooth). For Bluetooth photo printers such as Instax Link, Canon Ivy or HP Sprocket,
use **AirDrop / Share → the printer's app** or **Save Image**, then print from that app.

## Customising themes

Themes live in [`app/themes.py`](app/themes.py). Each one has:
- a name, emoji and tagline
- the scene prompt
- three print-frame colours

Add an entry, redeploy, and it appears on the operator screen and the guest carousel.
To narrow the list for an event (e.g. only winter and Christmas themes), use **Settings →
Themes guests can choose**. For one-off ideas the operator can pick **Custom**, or type
extra details (e.g. "add a birthday cake") under any theme.

## Cost

OpenRouter listed Seedream 5.0 Flash from about **$0.018 per image** when this was
written. Check the model page for current pricing and for any surcharge on 2K output.
Each **Restyle** is another generation. **Make samples** creates one per theme (10 in
total), and the **Test AI connection** button makes one.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Camera unavailable" | Safari needs HTTPS, so use the Railway URL. Allow access via the **aA** menu → Website Settings → Camera, then tap the camera area to retry. |
| Take photo is greyed out | The chosen camera isn't ready. Check the camera chip on the operator screen, start the camera on that device, or pick another one in Settings. |
| Guests don't see themselves | The live preview comes from the camera device, so check that device is online and its camera is running. |
| AI errors | Use **Test AI connection** to see the exact OpenRouter error. 401 means a bad key; 402 means you're out of credits. If `/images` is rejected, `auto` mode switches to chat completions on its own. You can force it with `OPENROUTER_API_MODE=chat`. |
| Photos vanish after deploy | Mount a Railway volume at `/data`. |
| Print isn't 4×6 | Choose the 4×6 paper size in the AirPrint options. The image is already 1800×1200 px at 300 dpi. |

## Project layout

```
app/
  main.py       FastAPI routes, WebSocket, media, QR and guest pages
  booth.py      live state machine (countdown → capture → AI → result), device roles,
                guest permissions, preview relay, theme samples
  ai.py         OpenRouter client (Seedream), auto fallback, mock mode
  printing.py   4×6" print layout with Pillow (frame, event name, date, QR)
  themes.py     theme list and prompts
  storage.py    photos on disk
  config.py     environment settings
static/         guest screen, operator, camera, guest download and landing pages
                (plain HTML/CSS/JS, no build step); static/samples/ for default samples
tests/          pytest suite (AI requests, print layout, booth flow, guest permissions,
                phone camera + preview relay, samples)
```
