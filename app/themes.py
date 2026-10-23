"""Booth themes. Add or edit entries here to change what the operator can pick."""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Prepended to every theme so the AI restyles the scene without changing who is in it.
IDENTITY_GUARD = (
    "Edit this photo booth picture. Keep every person exactly as they are: same faces, "
    "identities, facial features, skin tones, expressions, poses, body shapes and the same "
    "number of people in the same positions. Do not add or remove people. Keep it a "
    "photorealistic, flattering, well-lit group portrait. "
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

    def to_dict(self) -> dict:
        return asdict(self)


THEMES: list[Theme] = [
    Theme(
        id="winter",
        name="Winter Wonderland",
        emoji="❄️",
        tagline="Snow days & cosy vibes",
        prompt=(
            "Place them in a magical snowy winter landscape: snow-covered pine forest, gentle "
            "falling snowflakes, soft blue-hour light with warm fairy lights. Dress them in cosy "
            "knitted scarves, beanies and winter coats. Their breath faintly visible in the cold air."
        ),
        motion="Snowflakes drift down, fairy lights twinkle and their breath shows in the cold air.",
        frame="#e8f1fb", accent="#5b8fd6", ink="#1d3557",
    ),
    Theme(
        id="sun",
        name="Holidays in the Sun",
        emoji="🌴",
        tagline="Beach mode: on",
        prompt=(
            "Place them on a tropical beach holiday at golden hour: turquoise sea, white sand, "
            "palm trees, a colourful beach bar in the background. Give them summer outfits, "
            "sunglasses, flower leis and sun hats. Warm, sun-kissed, cheerful holiday postcard look."
        ),
        motion="Palm leaves sway in the breeze, waves roll onto the sand and sunlight glitters on the sea.",
        frame="#fff4dc", accent="#ff8a3d", ink="#7a3200",
    ),
    Theme(
        id="festival",
        name="Music Festival",
        emoji="🎪",
        tagline="Main stage energy",
        prompt=(
            "Place them at a huge outdoor music festival at sunset: crowd and colourful stage "
            "lights behind them, confetti in the air, bunting flags. Give them festival outfits "
            "with flower crowns, glitter face gems, bandanas and wristbands."
        ),
        motion="Stage lights sweep over the crowd and confetti flutters down through the air.",
        frame="#2b1145", accent="#ff4fa3", ink="#ffe8f4",
    ),
    Theme(
        id="lunar",
        name="Lunar New Year",
        emoji="🧧",
        tagline="Huat ah!",
        prompt=(
            "Place them in a festive Lunar New Year street celebration at night: rows of glowing "
            "red lanterns, gold decorations, a lion dance and fireworks in the background. Dress "
            "them in elegant red and gold festive outfits such as cheongsam and mandarin-collar "
            "jackets, some holding red packets and mandarin oranges."
        ),
        motion="Red lanterns sway, the lion dancer bobs behind them and fireworks burst in the night sky.",
        frame="#8f0d12", accent="#f6c453", ink="#fff3d6",
    ),
    Theme(
        id="lights",
        name="Festival of Lights",
        emoji="🪔",
        tagline="Shine bright",
        prompt=(
            "Place them in a joyful Deepavali / Diwali celebration: hundreds of glowing oil lamps "
            "(diyas), colourful rangoli on the floor, marigold garlands and sparklers. Dress them "
            "in rich festive outfits such as saris, kurtas and lehengas in jewel tones with gold "
            "detailing. Warm golden glow."
        ),
        motion="Diya flames flicker, sparklers fizz and warm golden light dances across the rangoli.",
        frame="#3d1a5b", accent="#f9a825", ink="#fff6e0",
    ),
    Theme(
        id="xmas",
        name="Christmas Cheer",
        emoji="🎄",
        tagline="Merry & bright",
        prompt=(
            "Place them in a cosy Christmas living room: decorated Christmas tree with twinkling "
            "lights, wrapped presents, a crackling fireplace with stockings. Give them festive "
            "Christmas jumpers and Santa hats or reindeer antlers. Warm, joyful holiday card look."
        ),
        motion="The fire crackles, the tree lights twinkle and the stockings sway gently.",
        frame="#0f4d2c", accent="#d62839", ink="#fdf6e3",
    ),
    Theme(
        id="80s",
        name="Totally 80s",
        emoji="📼",
        tagline="Radical, dude",
        prompt=(
            "Restyle as a 1980s portrait: big voluminous permed hair, neon windbreakers, shoulder "
            "pads, leg warmers, aviator sunglasses. Background is a retro synthwave sunset with a "
            "neon grid, palm silhouettes and chrome. Slight VHS film grain and saturated neon colours."
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
            "Restyle as a 1990s photo: oversized denim jackets, flannel shirts, scrunchies, "
            "bucket hats, chokers and baggy jeans. Background is a bold 90s pastel geometric "
            "pattern (Memphis design) like a school-portrait or mall photo studio. Shot on a "
            "disposable camera with direct flash and a date stamp feel."
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
            "Restyle as an early-2000s pop star photoshoot: frosted tips, butterfly clips, tinted "
            "rimless sunglasses, velour tracksuits, metallic and pink outfits, flip phones. "
            "Background is glossy chrome and iridescent bubbles with a glamorous red-carpet flash "
            "look and a soft glow."
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
            "Place them on a glamorous Hollywood red carpet premiere: velvet ropes, a wall of "
            "photographers with camera flashes, spotlights and gold stars. Dress them in black-tie "
            "outfits, tuxedos and evening gowns with elegant jewellery."
        ),
        motion="Photographers' flashes pop all around and spotlights sweep across the red carpet.",
        frame="#111111", accent="#d4af37", ink="#f5e6b8",
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
    return IDENTITY_GUARD + scene


VIDEO_PROMPT = (
    "Animate this photo booth picture into a short, joyful clip. Keep every person exactly "
    "the same: same faces, identities, outfits and positions, and no extra people. They smile, "
    "laugh, wave and lean in together naturally while looking at the camera. {motion} Gentle "
    "slow camera push-in. Photorealistic, smooth natural motion, no text."
)


def build_video_prompt(theme: Theme) -> str:
    return VIDEO_PROMPT.format(motion=theme.motion)


def all_themes() -> list[dict]:
    return [t.to_dict() for t in THEMES] + [CUSTOM_THEME.to_dict()]
