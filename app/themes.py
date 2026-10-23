"""Booth themes. Add or edit entries here to change what the operator can pick.

Every image prompt is built from these parts (wording follows proven "change the
location" photo-editing prompts):
  1. IDENTITY_GUARD: everyone stays clearly recognisable, faces and proportions untouched.
  2. A framing rule: keep the camera framing; full-body themes also ask for people shown
     head to toe at a believable scale.
  3. The theme's scene, written like a photographer's brief.
  4. PLACE_INTEGRATION for themes set somewhere else: replace the environment completely
     and match its light, weather and clothing to it.
  5. REALISM: "genuinely photographed there", not over-edited.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

IDENTITY_GUARD = (
    "Edit the attached photo booth picture. The people in it are real guests: keep every "
    "person clearly recognisable from the uploaded photo. Preserve each face exactly, with the "
    "same facial structure, eyes, nose, mouth, skin tone, natural facial details, skin texture, "
    "age and expression, and preserve their body proportions. Do not beautify, slim, smooth, "
    "de-age or swap any face. Keep the same number of people in the same positions and poses. "
    "Change only what the scene below describes: outfits, accessories, hair styling where "
    "stated, setting and lighting. Keep outfits tasteful and suitable for an all-ages event. "
)

KEEP_FRAMING = "Keep the original camera angle and framing. "

FULL_BODY_FRAMING = (
    "Keep the original camera angle and framing. Where their full bodies are visible, show "
    "them head to toe with their feet planted on the ground, at a believable scale for the "
    "setting, as if they were really photographed there. "
)

PLACE_INTEGRATION = (
    " Completely replace the original background with this location and naturally integrate "
    "everyone into it: match the scene's lighting, shadows, reflections, perspective, "
    "atmosphere, weather and colour temperature, and dress everyone for the location so their "
    "clothing suits the weather and behaves naturally there (no one keeps an outfit that would "
    "look out of place)."
)

REALISM = (
    " Make it look like they were genuinely photographed there with a professional full-frame "
    "camera: natural skin texture and facial detail, realistic fabric and hair, contact shadows "
    "where they touch the ground, realistic depth with subtle depth of field and authentic "
    "environmental detail. Polished but believable, without looking artificial or over-edited. "
    "No text, logos, watermarks or extra people."
)


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    emoji: str
    tagline: str
    prompt: str
    # Print frame colours (hex)
    frame: str
    accent: str
    ink: str
    # What moves when the photo is turned into a short video clip
    motion: str = "The scene comes gently to life around them."
    # Places that only look real with everyone in shot head to toe; the guest screen
    # and camera ask guests to step back for these.
    full_body: bool = False
    # Set somewhere else entirely (beach, mountains...): add PLACE_INTEGRATION.
    place: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


THEMES: list[Theme] = [
    Theme(
        id="winter",
        name="Winter Wonderland",
        emoji="❄️",
        tagline="Snow days & cosy vibes",
        prompt=(
            "Scene: on location in a real snowy pine forest at blue hour. Deep fresh snow on the "
            "ground, snow-laden spruce trees, warm string lights between the trees and gently "
            "falling snowflakes. Dress every person head to toe in winter clothes: knitted beanies, "
            "scarves, wool coats, warm trousers and winter boots. Cold blue ambient light with warm fill from the string lights; their breath "
            "faintly visible in the cold air."
        ),
        motion="Snowflakes drift down, fairy lights twinkle and their breath shows in the cold air.",
        full_body=True,
        place=True,
        frame="#e8f1fb", accent="#5b8fd6", ink="#1d3557",
    ),
    Theme(
        id="sun",
        name="Holidays in the Sun",
        emoji="🌴",
        tagline="Beach mode: on",
        prompt=(
            "Scene: on a real tropical beach at golden hour, standing on white sand near the "
            "water's edge, with a turquoise sea, gentle waves, leaning palm trees and a colourful "
            "beach bar in the distance. Dress every person head to toe in summer holiday clothes: "
            "linen shirts, sundresses, shorts, sandals, sunglasses, straw hats and flower leis. Warm low sun from the side "
            "with soft light reflected off the sea and sand."
        ),
        motion="Palm leaves sway in the breeze, waves roll onto the sand and sunlight glitters on the sea.",
        full_body=True,
        place=True,
        frame="#fff4dc", accent="#ff8a3d", ink="#7a3200",
    ),
    Theme(
        id="mountains",
        name="Mountain Adventure",
        emoji="🏔️",
        tagline="On top of the world",
        prompt=(
            "Scene: standing together on a rocky alpine ridge high in real snow-capped mountains, "
            "with a vast valley, a winding river and pine forests far below and dramatic peaks and "
            "drifting clouds behind them, at golden hour. Dress every person head to toe in outdoor "
            "hiking gear: puffer and shell jackets, beanies, hiking trousers, boots and small "
            "backpacks. Crisp mountain "
            "air, wind gently moving hair and clothing, warm low sunlight on their faces and long "
            "shadows across the rocks. A wide landscape photograph that shows the epic scale of the "
            "mountains around them."
        ),
        motion="Wind tugs at their jackets and hair, clouds drift across the peaks and an eagle glides far below.",
        full_body=True,
        place=True,
        frame="#e7eee9", accent="#2f6b4f", ink="#16261e",
    ),
    Theme(
        id="festival",
        name="Music Festival",
        emoji="🎪",
        tagline="Main stage energy",
        prompt=(
            "Scene: at a huge outdoor music festival at sunset, in the crowd area in front of the "
            "main stage, with colourful stage lights, haze, confetti in the air and bunting flags. "
            "Dress every person in boho festival outfits: flower crowns, glitter face gems, bandanas, "
            "fringed jackets, denim, ankle boots and wristbands. Warm sunset backlight with coloured stage light spilling onto them."
        ),
        motion="Stage lights sweep over the crowd and confetti flutters down through the air.",
        full_body=True,
        place=True,
        frame="#2b1145", accent="#ff4fa3", ink="#ffe8f4",
    ),
    Theme(
        id="lunar",
        name="Lunar New Year",
        emoji="🧧",
        tagline="Huat ah!",
        prompt=(
            "Scene: on a festive Chinatown street during Lunar New Year at night, under rows of "
            "glowing red lanterns and gold decorations, with a lion dance and fireworks in the "
            "background. Dress every person head to toe in elegant red and gold festive outfits such "
            "as cheongsam and mandarin-collar jackets; some hold red packets and mandarin oranges. Warm lantern light "
            "with a soft red glow on their faces."
        ),
        motion="Red lanterns sway, the lion dancer bobs behind them and fireworks burst in the night sky.",
        full_body=True,
        place=True,
        frame="#8f0d12", accent="#f6c453", ink="#fff3d6",
    ),
    Theme(
        id="lights",
        name="Festival of Lights",
        emoji="🪔",
        tagline="Shine bright",
        prompt=(
            "Scene: a joyful Deepavali / Diwali celebration in a courtyard at dusk, with rows of "
            "glowing oil lamps (diyas), colourful rangoli on the floor, marigold garlands and "
            "sparklers. Dress every person in rich festive outfits such as saris, kurtas, sherwanis "
            "and lehengas in jewel tones with gold detailing. Warm golden lamplight on their faces."
        ),
        motion="Diya flames flicker, sparklers fizz and warm golden light dances across the rangoli.",
        place=True,
        frame="#3d1a5b", accent="#f9a825", ink="#fff6e0",
    ),
    Theme(
        id="xmas",
        name="Christmas Cheer",
        emoji="🎄",
        tagline="Merry & bright",
        prompt=(
            "Scene: a cosy living room on Christmas Eve, with a decorated tree and twinkling "
            "lights, wrapped presents and a crackling fireplace hung with stockings. Dress every "
            "person in a festive Christmas jumper with a Santa hat or reindeer antlers. Warm tungsten light from "
            "the fire and fairy lights, like a candid family holiday photo."
        ),
        motion="The fire crackles, the tree lights twinkle and the stockings sway gently.",
        place=True,
        frame="#0f4d2c", accent="#d62839", ink="#fdf6e3",
    ),
    Theme(
        id="80s",
        name="Totally 80s",
        emoji="📼",
        tagline="Radical, dude",
        prompt=(
            "Scene: a genuine 1980s studio portrait. Restyle their outfits and hair in authentic "
            "80s fashion: big voluminous hair, neon windbreakers, shoulder pads, leg warmers and "
            "aviator sunglasses. Backdrop: a retro synthwave sunset with a neon grid and palm "
            "silhouettes. Shot on 35 mm film with saturated colours, soft flash and light grain."
        ),
        motion="Neon lights pulse, the synthwave sun glows on the horizon and a soft VHS shimmer rolls across.",
        frame="#14082b", accent="#ff2bd6", ink="#2de2ff",
    ),
    Theme(
        id="90s",
        name="90s Throwback",
        emoji="💿",
        tagline="As if!",
        prompt=(
            "Scene: a real 1990s mall photo-studio portrait. Restyle their outfits in authentic "
            "90s fashion: oversized denim jackets, flannel shirts, scrunchies, bucket hats, chokers "
            "and baggy jeans. Backdrop: a bold pastel geometric Memphis-pattern studio backdrop. "
            "Shot on a disposable film camera with direct on-camera flash, slightly washed-out "
            "colours and a faint date stamp."
        ),
        motion="A disposable-camera flash pops and the pastel shapes behind them shift playfully.",
        frame="#fdf0ff", accent="#7b2ff7", ink="#2a0a4a",
    ),
    Theme(
        id="y2k",
        name="Y2K 2000s",
        emoji="📱",
        tagline="That's hot",
        prompt=(
            "Scene: an early-2000s pop-star photoshoot. Restyle their outfits and accessories in "
            "authentic Y2K fashion: velour tracksuits, metallic and pink tops, butterfly clips, "
            "frosted tips, tinted rimless sunglasses and flip phones. Backdrop: glossy chrome and "
            "iridescent bubbles. Bright glamorous flash with a soft glow, like a 2002 magazine shoot."
        ),
        motion="Iridescent bubbles float past, camera flashes sparkle and everything has a glossy glow.",
        frame="#ffe3f3", accent="#ff3ea5", ink="#5a0a3c",
    ),
    Theme(
        id="hollywood",
        name="Red Carpet",
        emoji="🎬",
        tagline="Lights, camera, action",
        prompt=(
            "Scene: arriving on the red carpet at a Hollywood film premiere at night, with velvet "
            "ropes, a step-and-repeat wall, a crowd of photographers with flashes popping, "
            "spotlights and gold stars. Dress every person head to toe in black tie: tailored "
            "tuxedos and floor-length evening gowns with elegant jewellery. Bright paparazzi flash on them against dramatic "
            "background lighting."
        ),
        motion="Photographers' flashes pop all around and spotlights sweep across the red carpet.",
        full_body=True,
        place=True,
        frame="#111111", accent="#d4af37", ink="#f5e6b8",
    ),
    Theme(
        id="fashion",
        name="Fashion Shoot",
        emoji="👗",
        tagline="Serve the look",
        prompt=(
            "Scene: a high-end editorial fashion shoot suitable for a major magazine, in a large "
            "professional photo studio with a seamless warm-grey paper backdrop curving into the "
            "floor. Restyle every person head to toe in new statement designer looks, clearly "
            "different from what they arrived in: sharply tailored suits in bold colours, "
            "sculptural coats, silk and satin gowns, statement accessories and polished shoes. "
            "Confident editorial composition, carefully controlled lighting from a large softbox "
            "key light with subtle rim lights, and polished but believable colour grading, shot on "
            "a medium-format camera. Do not add magazine text or logos."
        ),
        motion="Studio strobes flash, a fan gently lifts their hair and clothes and they settle into confident model poses.",
        full_body=True,
        frame="#f3eee8", accent="#1a1a1a", ink="#1a1a1a",
    ),
    Theme(
        id="noir",
        name="Black & White Studio",
        emoji="🖤",
        tagline="Timeless & dramatic",
        prompt=(
            "Scene: a dramatic black-and-white studio portrait. Plain dark seamless backdrop, one "
            "hard key light from the side casting deep shadows (chiaroscuro) and a crisp rim light "
            "separating them from the background. Dress every person in simple, elegant black "
            "clothing. "
            "Render the whole image in high-contrast monochrome black and white, with rich deep "
            "blacks, bright highlights and fine film grain, like a classic gallery print."
        ),
        motion=(
            "The key light shifts slowly and they share a laugh, with subtle film grain. The whole "
            "clip stays in high-contrast black and white."
        ),
        frame="#0b0b0b", accent="#f5f5f5", ink="#f5f5f5",
    ),
]

CUSTOM_THEME = Theme(
    id="custom",
    name="Custom",
    emoji="✨",
    tagline="Your own idea",
    prompt="",
    frame="#ffffff", accent="#222222", ink="#222222",
)

_BY_ID = {t.id: t for t in THEMES}


def get_theme(theme_id: str) -> Theme:
    if theme_id == CUSTOM_THEME.id:
        return CUSTOM_THEME
    return _BY_ID.get(theme_id, THEMES[0])


def build_prompt(theme: Theme, custom_prompt: str = "") -> str:
    """Final text sent to the image model.

    For the Custom theme the operator's text is the whole scene; for any other theme it is
    appended as extra detail (e.g. "add a birthday cake").
    """
    extra = custom_prompt.strip()
    if theme.id == CUSTOM_THEME.id:
        scene = extra or "Give the photo a fun, colourful party look."
    else:
        scene = theme.prompt + (f" Also: {extra}" if extra else "")
    framing = FULL_BODY_FRAMING if theme.full_body else KEEP_FRAMING
    place = PLACE_INTEGRATION if theme.place else ""
    return IDENTITY_GUARD + framing + scene + place + REALISM


VIDEO_PROMPT = (
    "Animate this photo booth picture into a short, joyful clip. Keep every person exactly "
    "the same: same faces, facial features, skin tones, outfits, body proportions and "
    "positions, and no extra people. They smile, laugh, wave and lean in together naturally "
    "while looking at the camera. {motion} Gentle slow camera push-in. Photorealistic, smooth "
    "natural motion, no text."
)


def build_video_prompt(theme: Theme) -> str:
    return VIDEO_PROMPT.format(motion=theme.motion)


def all_themes() -> list[dict]:
    return [t.to_dict() for t in THEMES] + [CUSTOM_THEME.to_dict()]
