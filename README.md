# 📸 Fun Booth

An AI photo booth that runs in Safari on two iPads. Guests strike a pose, the AI
(ByteDance **Seedream 5.0 Flash** via OpenRouter) restyles them into a theme, and
the operator prints the photo or AirDrops it. Guests can also scan a QR code to
download it.

**Themes included:** Winter Wonderland · Holidays in the Sun · Music Festival ·
Lunar New Year · Festival of Lights · Christmas Cheer · Totally 80s · 90s Throwback ·
Y2K 2000s · Red Carpet · Custom (type any scene)

```
 ┌───────────── Operator iPad ─────────────┐        ┌────────── Display iPad (faces guests) ──────────┐
 │ pick theme · take photo · restyle       │  live  │ live mirror · 3-2-1 countdown · flash           │
 │ print preview → AirPrint · AirDrop      │◄──────►│ “creating your magic…” · result + QR + AirDrop  │
 │ gallery of recent shots · settings      │  sync  │                                                 │
 └─────────────────────────────────────────┘        └─────────────────────────────────────────────────┘
                         ▲                                         ▲
                         └──────────── Railway (FastAPI) ──────────┘
                                         │
                                         ▼
                        OpenRouter → bytedance-seed/seedream-5-0-flash
```

## How a photo is taken

1. The operator picks a theme and taps **Take photo**.
2. The display shows a countdown, flashes, and its camera captures the frame. You can
   switch the camera to the operator iPad in Settings.
3. The server sends the photo and the theme prompt to Seedream. Every prompt starts
   with an instruction to keep faces, poses and the number of people unchanged.
4. The result appears on both iPads, with a QR code on the display.
5. From there the operator can:
   - **Print:** opens a print preview of a framed 6×4" (or 4×6") card at 300 dpi
     showing the event name, date and a QR code. AirPrint then sends it to the printer.
   - **AirDrop:** opens the iPad share sheet with the framed and plain versions.
   - **Restyle:** re-runs the same shot with a different theme.
   - **Next guest:** goes back to the live camera.

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
| `BOOTH_PIN` | random, printed in logs | PIN to unlock both iPads and the API |
| `EVENT_NAME` | `Fun Booth` | Initial event name (editable in the app) |
| `OPENROUTER_MODEL` | `bytedance-seed/seedream-5-0-flash` | Any OpenRouter image model that accepts an input image |
| `OPENROUTER_API_MODE` | `auto` | `images` (unified `/images` API), `chat` (`/chat/completions` with image output), or `auto` (try `/images`, fall back to chat) |
| `OPENROUTER_RESOLUTION` | `2K` | `1K` is cheaper and faster; `2K` prints sharper. Empty uses the model default |
| `OPENROUTER_TIMEOUT` | `120` | Seconds to wait for the AI |
| `TIMEZONE` | `UTC` | Time zone for the date on prints |
| `DATA_DIR` | `/data` in Docker | Where photos are stored (mount a volume here) |
| `PUBLIC_URL` | Railway domain | Override the URL used in QR codes, e.g. for a custom domain |

## Setting up the iPads

**Display iPad** (faces the guests)
1. In Safari open `https://<your-app>/display`, enter the PIN and tap **Start display**,
   then allow camera access.
2. For a full-screen kiosk, tap Share → **Add to Home Screen** and launch it from there.
3. Set Settings → Display & Brightness → **Auto-Lock → Never**, and turn on
   **Guided Access** (Settings → Accessibility) so guests can't leave the app.
4. The faint ⚙︎ in the top-right corner switches between the front and back camera.

**Operator iPad**
1. Open `https://<your-app>/operator` and enter the PIN.
2. Check that the status chips show **Server**, **Display** and **Display camera** in
   green.
3. Use ⚙️ Settings for:
   - event name
   - which iPad takes the photo
   - countdown length
   - print layout (landscape 6×4 or portrait 4×6)
   - QR code on/off for prints and the display
   - uploading a photo instead of using the camera
   - testing the AI connection

Both iPads only need internet access. They don't have to be on the same Wi-Fi.

## Printing

Printing uses **AirPrint** from the operator iPad: **Print → preview → Print →
choose printer**. In the print options pick **4×6 / 10×15 cm** paper and the number of
copies. Any AirPrint photo printer works. Canon SELPHY dye-sub printers are a popular
choice for booths; check that the model you buy lists AirPrint. Printers without
AirPrint, such as many DNP/Mitsubishi event printers, need a print server or the
maker's iPad app.

## Sharing: AirDrop, QR and Bluetooth

- **AirDrop** (operator and display): opens the iPad share sheet with the framed and
  plain photos. AirDrop uses Bluetooth plus Wi-Fi, and guests receive the photos
  straight into their iPhone's Photos.
- **QR code** (display and print): any phone, Android included, scans it to reach a
  download page.
- **Bluetooth printers and other apps:** Safari can't talk to Bluetooth devices
  directly (iOS doesn't support Web Bluetooth). For Bluetooth photo printers such as
  Instax Link, Canon Ivy or HP Sprocket, use **AirDrop → share sheet → the printer's
  app** or **Save Image**, then print from the printer's app.

## Customising themes

Themes live in [`app/themes.py`](app/themes.py). Each one has:
- a name, emoji and tagline
- the scene prompt
- three print-frame colours

Add an entry, redeploy, and it appears on the operator iPad. For one-off ideas use the
**Custom** theme, or type extra details (e.g. "add a birthday cake") under any theme.

## Cost

OpenRouter listed Seedream 5.0 Flash from about **$0.018 per image** when this was
written. Check the model page for current pricing and for any surcharge on 2K output.
Each **Restyle** is another generation. The **Test AI connection** button makes one.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Camera unavailable" | Safari needs HTTPS, so use the Railway URL. Allow access via the **aA** menu → Website Settings → Camera, then tap the camera area to retry. |
| Take photo is greyed out | The chosen camera iPad isn't ready. Tap **Start display** on the display iPad, or switch the camera in Settings. |
| AI errors | Use **Test AI connection** to see the exact OpenRouter error. 401 means a bad key; 402 means you're out of credits. If `/images` is rejected, `auto` mode switches to chat completions on its own. You can force it with `OPENROUTER_API_MODE=chat`. |
| Photos vanish after deploy | Mount a Railway volume at `/data`. |
| Print isn't 4×6 | Choose the 4×6 paper size in the AirPrint options. The image is already 1800×1200 px at 300 dpi. |

## Project layout

```
app/
  main.py       FastAPI routes, WebSocket, media, QR and guest pages
  booth.py      live state machine (countdown → capture → AI → result) + device sync
  ai.py         OpenRouter client (Seedream), auto fallback, mock mode
  printing.py   4×6" print layout with Pillow (frame, event name, date, QR)
  themes.py     theme list and prompts
  storage.py    photos on disk
  config.py     environment settings
static/         operator, display, guest and landing pages (plain HTML/CSS/JS, no build step)
tests/          pytest suite (AI request shapes, print layout, full booth flow)
```
