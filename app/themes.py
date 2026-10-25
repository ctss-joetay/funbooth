"""Booth themes. Add or edit entries here to change what the operator can pick.

Every image prompt is built from these parts (wording follows proven "change the
location" photo-editing prompts):
  1. IDENTITY_GUARD: everyone stays clearly recognisable, faces and proportions untouched.
  2. A framing rule chosen per shot, so every theme works both ways: full body (everyone
     head to toe at a believable scale) or face only (a close-up, with a reminder after the
     scene so outfit details like shoes don't make the model zoom out).
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
    "stated, setting and lighting. Keep outfits tasteful, with modest necklines and hemlines, "
    "suitable for an all-ages event. "
)

FULL_BODY_FRAMING = (
    "Keep the original camera angle and framing. Where their full bodies are visible, show "
    "them head to toe with their feet planted on the ground and contact shadows where they "
    "touch it, at a believable scale for the setting, as if they were really photographed there. "
)

FACE_FRAMING = (
    "Keep the original camera angle and the same close crop. This is a close-up portrait "
    "framed on their faces and shoulders, with every face large, sharp and in focus. "
)

FACE_FRAMING_END = (
    " Keep the same close-up crop as the original photo: do not zoom out or show more of "
    "their bodies, and leave anything from the scene that would fall below the frame (such as "
    "trousers, skirts or shoes) out of shot."
)

# Guests pick one on the pose screen; it applies to every theme: (before the scene, after it).
FRAMINGS = {"full": (FULL_BODY_FRAMING, ""), "face": (FACE_FRAMING, FACE_FRAMING_END)}

PLACE_INTEGRATION = (
    " Completely replace the original background with this location and naturally integrate "
    "everyone into it: match the scene's lighting, shadows, reflections, perspective, "
    "atmosphere, weather and colour temperature. Give every person a complete new outfit and "
    "footwear for the location, clearly different from what they arrived in, so their clothing "
    "suits the weather and behaves naturally there (no one keeps an outfit that would look out "
    "of place)."
)

REALISM = (
    " Make it look like they were genuinely photographed there with a professional full-frame "
    "camera: natural skin texture and facial detail, realistic fabric and hair, realistic depth "
    "with subtle depth of field and authentic environmental detail. Polished but believable, "
    "without looking artificial or over-edited. No text, logos, watermarks or extra people."
)


# Theme groups, in the order guests see them.
PLACES = "🌍 Places"
DRESS_UP = "🦸 Dress up"
ERAS = "📼 Eras & styles"
PORTRAITS = "📸 Portraits"


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
    # Set somewhere else entirely (beach, mountains...): add PLACE_INTEGRATION.
    place: bool = False
    # Group on the guest carousel's tabs and the operator's theme list
    category: str = ""

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
        place=True,
        frame="#e8f1fb", accent="#5b8fd6", ink="#1d3557",
        category=PLACES,
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
        place=True,
        frame="#fff4dc", accent="#ff8a3d", ink="#7a3200",
        category=PLACES,
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
            "shadows across the rocks, with the epic scale of the mountains all around them."
        ),
        motion="Wind tugs at their jackets and hair, clouds drift across the peaks and an eagle glides far below.",
        place=True,
        frame="#e7eee9", accent="#2f6b4f", ink="#16261e",
        category=PLACES,
    ),
    Theme(
        id="paris",
        name="Paris Getaway",
        emoji="🗼",
        tagline="Bonjour from the Eiffel Tower",
        prompt=(
            "Scene: on location in Paris on a real spring evening at golden hour, standing on the "
            "Trocadéro terrace with the Eiffel Tower rising behind them across the Seine, elegant "
            "cream stone buildings, blossoming trees and soft pink clouds. Dress every person head "
            "to toe in chic Parisian outfits: trench coats, striped tops, berets, silk scarves, "
            "tailored trousers or midi skirts, and loafers or ankle boots. Warm low sunlight from "
            "the side with a soft golden glow on their faces, like a travel magazine photo."
        ),
        motion="The Eiffel Tower's lights begin to sparkle, scarves flutter in the breeze and pigeons take off behind them.",
        place=True,
        frame="#fbeff0", accent="#2b3a67", ink="#1d2445",
        category=PLACES,
    ),
    Theme(
        id="tokyo",
        name="Tokyo Nights",
        emoji="🏙️",
        tagline="Neon city lights",
        prompt=(
            "Scene: on location in Tokyo at night, standing on the pavement beside the famous "
            "Shibuya scramble crossing, with towering buildings covered in glowing neon signs and "
            "giant video screens (no readable writing or logos), light rain on the street "
            "reflecting the colourful lights, and blurred crowds and taxis behind them. Dress every "
            "person head to toe in stylish Tokyo street fashion for a cool, damp night: oversized "
            "jackets, layered hoodies, wide trousers and sneakers, with a few clear umbrellas. "
            "Colourful pink, blue and purple neon light on their faces and glossy reflections on "
            "the wet ground, like a cinematic night street photo."
        ),
        motion="Neon signs flicker, crowds flow across the crossing behind them and raindrops glint in the light.",
        place=True,
        frame="#0d0b1f", accent="#ff2e88", ink="#e9f1ff",
        category=PLACES,
    ),
    Theme(
        id="newyork",
        name="New York City",
        emoji="🗽",
        tagline="Big city, bright lights",
        prompt=(
            "Scene: on location in New York City on a crisp autumn evening at dusk, standing in "
            "Times Square surrounded by "
            "towering buildings with huge glowing screens showing colourful abstract images (no "
            "readable text or brand logos), yellow taxis passing and city crowds blurred behind "
            "them. Dress every person head to toe in smart city outfits: tailored coats, leather "
            "jackets, knitwear, jeans or smart trousers, scarves and boots. Bright, colourful light "
            "from the screens mixed with the deep blue dusk sky, like a big-city travel photo."
        ),
        motion="The giant screens glow and change colour, yellow taxis rush past and the city lights flicker on.",
        place=True,
        frame="#fff6d6", accent="#f7b500", ink="#1a1a1a",
        category=PLACES,
    ),
    Theme(
        id="safari",
        name="Safari Adventure",
        emoji="🦒",
        tagline="Wild & free",
        prompt=(
            "Scene: on location on the African savannah at golden hour, standing beside an open "
            "safari jeep on a dusty track, with acacia trees, golden grassland, zebras and giraffes "
            "grazing at a safe distance and a big orange sky. Dress every person head to toe in "
            "safari clothes: khaki and olive shirts, utility vests, cargo trousers, wide-brimmed "
            "hats, binoculars and sturdy boots. Warm low sun with a golden haze and long shadows "
            "across the grass, like a wildlife travel photo."
        ),
        motion="Giraffes stroll in the distance, the tall grass sways and dust drifts in the golden light.",
        place=True,
        frame="#f3e3c3", accent="#c27b2e", ink="#4a2c0f",
        category=PLACES,
    ),
    Theme(
        id="gardens",
        name="Gardens by the Bay",
        emoji="🌳",
        tagline="Singapore after dark",
        prompt=(
            "Scene: on location at Gardens by the Bay in Singapore at night, standing on a garden "
            "path in the Supertree Grove, with the giant tree-like vertical gardens glowing purple, "
            "blue and pink above them, lush tropical plants around them and the Marina Bay skyline "
            "in the distance. Dress every person head to toe in smart-casual outfits for a warm "
            "tropical evening: light linen shirts, summer dresses, breathable trousers and "
            "comfortable shoes. Colourful light from the Supertrees with a soft glow on their "
            "faces, like a night travel photo."
        ),
        motion="The Supertrees pulse with changing colours and lights shimmer across the skyline behind them.",
        place=True,
        frame="#0f1d3a", accent="#b05cff", ink="#eaf6ff",
        category=PLACES,
    ),
    Theme(
        id="space",
        name="Space Explorers",
        emoji="🚀",
        tagline="One small step…",
        prompt=(
            "Scene: standing together on the surface of the Moon, with grey dusty ground and "
            "footprints, a lunar lander behind them and the Earth rising in the black, starry sky. "
            "Dress every person head to toe in realistic white astronaut spacesuits with mission "
            "patches (no real agency logos), holding their helmets under their arms so their faces "
            "are fully visible. Hard, bright sunlight from one side with deep shadows and the blue "
            "glow of the Earth, like a real space mission photo."
        ),
        motion="Moon dust drifts slowly around their boots, stars twinkle and the Earth glows in the sky.",
        place=True,
        frame="#0b1026", accent="#6ec1ff", ink="#e8f0ff",
        category=DRESS_UP,
    ),
    Theme(
        id="superhero",
        name="Superheroes",
        emoji="🦸",
        tagline="Save the day",
        prompt=(
            "Scene: standing heroically together on a city rooftop at sunset, with skyscrapers all "
            "around, a dramatic sky with beams of light breaking through the clouds and the city "
            "glowing below. Dress every person head to toe in original superhero costumes (not any "
            "existing character): bold fitted suits in different colours, each with their own "
            "simple emblem such as a star, wave, leaf or geometric shape (no lightning bolts or "
            "letters), flowing capes, utility belts and boots, with their faces uncovered. Dramatic "
            "cinematic lighting with a warm sunset rim light, like a still from a superhero movie."
        ),
        motion="Capes billow in the wind, light beams sweep through the clouds and the city sparkles below.",
        place=True,
        frame="#13213f", accent="#e63946", ink="#fff3d1",
        category=DRESS_UP,
    ),
    Theme(
        id="sports",
        name="Sports Champions",
        emoji="🏆",
        tagline="Winning team",
        prompt=(
            "Scene: on the pitch of a packed football stadium at night just after winning the "
            "final, with bright floodlights, a cheering crowd in the stands, confetti falling and a "
            "big gold trophy held up between them. Dress every person head to toe in matching team "
            "kits: jerseys in the same bold colours (no brand logos or sponsor names), shorts, "
            "socks and studded football boots (no one in heels or sandals), with gold winners' "
            "medals around their necks. Bright "
            "stadium floodlights and colourful confetti, like a sports magazine celebration photo."
        ),
        motion="Confetti rains down, the crowd waves flags and camera flashes pop around the stadium.",
        place=True,
        frame="#0e3b24", accent="#ffd23f", ink="#f2fff6",
        category=DRESS_UP,
    ),
    Theme(
        id="kpop",
        name="K-pop Stage",
        emoji="🎤",
        tagline="Idol energy",
        prompt=(
            "Scene: on a huge K-pop concert stage, standing together at the front of the stage with "
            "giant LED screens, sweeping coloured spotlights, haze and sparkling confetti, and "
            "glowing light sticks in the dark arena. Dress every person head to toe in coordinated, "
            "stylish K-pop stage outfits in a matching colour palette: embellished jackets, "
            "tailored trousers or skirts, statement boots and in-ear monitors. Bright pink and "
            "purple stage lighting with a glossy concert look, like an official concert photo."
        ),
        motion="Spotlights sweep, confetti bursts over the stage and the LED screens pulse to the beat.",
        place=True,
        frame="#1a0b2e", accent="#ff5ecf", ink="#f9e9ff",
        category=DRESS_UP,
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
        place=True,
        frame="#111111", accent="#d4af37", ink="#f5e6b8",
        category=DRESS_UP,
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
        place=True,
        frame="#2b1145", accent="#ff4fa3", ink="#ffe8f4",
        category=DRESS_UP,
    ),
    Theme(
        id="classroom",
        name="Classroom Days",
        emoji="🏫",
        tagline="Back to school",
        prompt=(
            "Scene: inside a real, sunlit school classroom on a bright morning, with rows of "
            "wooden desks and chairs around them, with a green chalkboard covered in chalk doodles and "
            "maths diagrams (no readable words), a globe, stacks of books, a few potted plants and "
            "tall windows with sunlight streaming in. Dress every person head to toe in neat "
            "school uniforms: crisp white shirts, ties or ribbon bows, navy blazers or cardigans, "
            "pleated skirts or tailored trousers, socks and polished school shoes; some hold "
            "books or a school bag. Warm natural window light with soft shadows, like a "
            "nostalgic class photo."
        ),
        motion="Sunlight streams through the windows, chalk dust floats in the light and pages flutter on the desks.",
        place=True,
        frame="#2f4f3a", accent="#f2c94c", ink="#fdf8e8",
        category=DRESS_UP,
    ),
    Theme(
        id="graduation",
        name="Graduation Day",
        emoji="🎓",
        tagline="Caps in the air",
        prompt=(
            "Scene: on location on a real university campus on a sunny graduation day, standing on "
            "the steps in front of a grand old stone building with tall columns, with green lawns, "
            "leafy trees and other families celebrating far behind them. Dress every person head to "
            "toe in graduation attire: flowing black academic gowns with coloured hoods and smart "
            "clothes and polished shoes underneath, and every one of them wears a square black "
            "mortarboard cap with a tassel, fully in the frame; some hold "
            "rolled diplomas tied with ribbon or bouquets of flowers. Bright, warm late-morning "
            "sunlight with soft shadows, like a proud graduation day photo."
        ),
        motion="Tassels sway in the breeze, a few caps fly up into the sky behind them and flower petals drift down.",
        place=True,
        frame="#14213d", accent="#fca311", ink="#f5f1e8",
        category=DRESS_UP,
    ),
    Theme(
        id="70s",
        name="70s Disco",
        emoji="🪩",
        tagline="Boogie wonderland",
        prompt=(
            "Scene: a genuine 1970s disco night on a glowing light-up dance floor under a spinning "
            "mirror ball, with coloured spotlights and sparkles of reflected light. Restyle their "
            "outfits and hair in authentic 70s disco fashion: flared trousers, wide-collar shirts, "
            "sequinned and metallic jumpsuits, platform shoes, big feathered or curly hair and "
            "tinted glasses. Warm, saturated film colours with a soft glow and light grain, like a "
            "photo from a 1970s nightclub."
        ),
        motion="The mirror ball spins, scattering sparkles of light, and the dance floor tiles flash in colour.",
        frame="#2b1408", accent="#ffb627", ink="#ffe9c7",
        category=ERAS,
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
        category=ERAS,
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
        category=ERAS,
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
        category=ERAS,
    ),
    Theme(
        id="wildwest",
        name="Wild West",
        emoji="🤠",
        tagline="Yee-haw!",
        prompt=(
            "Scene: on location on the dusty main street of an old Wild West frontier town at "
            "sunset, with wooden saloon fronts, hitching posts, horses, tumbleweed and red desert "
            "mesas in the distance. Dress every person head to toe in classic cowboy and frontier "
            "outfits: cowboy hats, bandanas, leather vests, fringed jackets, prairie dresses, "
            "denim, big belt buckles and cowboy boots, with no weapons. Warm, dusty sunset light "
            "with long shadows and slightly faded film colours, like a still from a classic western."
        ),
        motion="Tumbleweed rolls past, dust swirls in the warm light and a horse flicks its tail behind them.",
        place=True,
        frame="#f0dcc0", accent="#a0522d", ink="#3b2414",
        category=ERAS,
    ),
    Theme(
        id="cyberpunk",
        name="Cyberpunk City",
        emoji="🤖",
        tagline="Welcome to 2099",
        prompt=(
            "Scene: on location on a rain-soaked street in a futuristic megacity at night, with "
            "towering skyscrapers, flying vehicles, holographic displays and glowing cyan and "
            "magenta neon (no readable writing), steam rising from the ground and puddles "
            "reflecting the lights. Dress every person head to toe in futuristic techwear: sleek "
            "black jackets with glowing LED trim, reflective panels, high-tech glasses, utility "
            "straps and chunky boots. Moody cinematic lighting with strong cyan and magenta rim "
            "light, like a still from a sci-fi film."
        ),
        motion="Neon lights flicker, flying cars glide overhead and rain drifts through the glowing haze.",
        place=True,
        frame="#05060f", accent="#00e5ff", ink="#f2e9ff",
        category=ERAS,
    ),
    Theme(
        id="kawaii",
        name="Kawaii Harajuku",
        emoji="🎀",
        tagline="Cute Tokyo street style",
        prompt=(
            "Scene: on location on a real pastel shopping street in Harajuku, Tokyo, on a bright "
            "spring afternoon, with colourful shopfronts, a crêpe stand, cherry blossom trees and "
            "strings of colourful bunting overhead. Dress every person head to toe in colourful "
            "Harajuku street fashion: pastel oversized hoodies, cardigans and jackets, wide-leg "
            "trousers or long skirts, chunky platform sneakers, colourful hair clips, bows and bag "
            "charms, and novelty sunglasses. Soft, bright daylight with a pastel pink, mint and "
            "lilac palette, like a Tokyo street-style magazine photo. Shop signs have no readable "
            "writing."
        ),
        motion="Cherry blossom petals drift past, the bunting flutters and they strike cute peace-sign poses.",
        place=True,
        frame="#ffe4f1", accent="#ff6fae", ink="#5b1a4a",
        category=ERAS,
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
        frame="#f3eee8", accent="#1a1a1a", ink="#1a1a1a",
        category=PORTRAITS,
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
        category=PORTRAITS,
    ),
    Theme(
        id="goldenhour",
        name="Golden Hour Portrait",
        emoji="🌅",
        tagline="Warm & glowing",
        prompt=(
            "Scene: a professional golden-hour portrait outdoors. Replace the background with a "
            "meadow of tall grass and wildflowers with soft rolling hills behind them, and match "
            "the light on everyone to it. Keep everyone's own outfits and hairstyles. Warm natural "
            "sunlight from low behind them, soft highlights, golden rim light on their hair, "
            "realistic shadows, natural colours, authentic environmental detail and subtle depth "
            "of field, so it looks genuinely photographed at golden hour."
        ),
        motion="Warm sunlight flickers through the swaying grass, wildflowers bob in the breeze and a soft lens flare glows.",
        frame="#fff1dc", accent="#f08a24", ink="#5a2e0c",
        category=PORTRAITS,
    ),
    Theme(
        id="polaroid",
        name="Polaroid Party",
        emoji="📸",
        tagline="Instant memories",
        prompt=(
            "Scene: a candid snapshot at a lively house party at night. Replace the background "
            "with a cosy room decorated with fairy lights, colourful balloons and streamers. Keep "
            "everyone's own outfits and hairstyles. Render the whole image like a real 1990s "
            "instant-film snapshot, clearly different from a modern digital photo: a harsh, "
            "slightly overexposed on-camera flash that brightens their faces and throws hard "
            "shadows on the wall behind them, a dark falloff into the room, faded low-contrast "
            "colours with a warm yellow and soft teal cast, a warm light leak in one corner, a "
            "strong vignette and visible film grain. Fill the whole image, with no border or frame."
        ),
        motion="Fairy lights twinkle, balloons bob and a camera flash pops as they laugh together.",
        frame="#fbf8f1", accent="#ff6b6b", ink="#2a2a2a",
        category=PORTRAITS,
    ),
]

CUSTOM_THEME = Theme(
    id="custom",
    name="Custom",
    emoji="✨",
    tagline="Your own idea",
    prompt="",
    frame="#ffffff", accent="#222222", ink="#222222",
    category="✨ Your own",
)

_BY_ID = {t.id: t for t in THEMES}


def get_theme(theme_id: str) -> Theme:
    if theme_id == CUSTOM_THEME.id:
        return CUSTOM_THEME
    return _BY_ID.get(theme_id, THEMES[0])


def build_prompt(theme: Theme, custom_prompt: str = "", framing: str = "full") -> str:
    """Final text sent to the image model.

    For the Custom theme the operator's text is the whole scene; for any other theme it is
    appended as extra detail (e.g. "add a birthday cake"). `framing` is "full" or "face".
    """
    extra = custom_prompt.strip()
    if theme.id == CUSTOM_THEME.id:
        scene = extra or "Give the photo a fun, colourful party look."
    else:
        scene = theme.prompt + (f" Also: {extra}" if extra else "")
    lead, end = FRAMINGS.get(framing, FRAMINGS["full"])
    place = PLACE_INTEGRATION if theme.place else ""
    return IDENTITY_GUARD + lead + scene + place + end + REALISM


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
