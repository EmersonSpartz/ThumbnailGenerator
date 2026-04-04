"""
Layout Library v4 — Split-screen dominant.

Data from hundreds of generations says split-screen/before-after is the only
consistently winning structure. This version goes all-in on that.

Every split-screen variant describes a specific LEFT→RIGHT contrast. This
constrains Claude enough that it can't wander into boring metaphors — the
structure forces a clear, instantly readable composition.

A small number of non-split layouts are kept as variety (S-tier proven only).
"""

import random

# ─── SPLIT-SCREEN LAYOUTS ─────────────────────────────────────────────────
# These are ALL split-screen: left side shows one thing, right side shows
# the contrasting thing. Vertical dividing line. Instantly readable.

TIER_S = [
    # === TIME / TRANSFORMATION SPLITS ===
    {
        "id": "split_pristine_destroyed",
        "name": "Split: Pristine → Destroyed",
        "instruction": "Vertical split. Left: something clean, perfect, polished, gleaming. Right: the SAME thing utterly destroyed — smashed, burned, crumbled to rubble. Total devastation.",
    },
    {
        "id": "split_solid_melting",
        "name": "Split: Solid → Melting",
        "instruction": "Vertical split. Left: something solid, stable, confident. Right: the SAME thing actively melting, dripping, losing all form. Pools of liquid below.",
    },
    {
        "id": "split_new_ancient",
        "name": "Split: New → Ancient",
        "instruction": "Vertical split. Left: something brand new, modern, gleaming tech. Right: the SAME thing aged thousands of years — crumbling, fossilized, covered in moss and decay.",
    },
    {
        "id": "split_small_massive",
        "name": "Split: Small → Massive",
        "instruction": "Vertical split. Left: something tiny, harmless, palm-sized. Right: the SAME thing grown to terrifying building-sized scale, looming and threatening.",
    },
    {
        "id": "split_one_swarm",
        "name": "Split: One → Swarm",
        "instruction": "Vertical split. Left: a single thing, alone, isolated. Right: that same thing multiplied into hundreds filling the entire frame. Unstoppable replication.",
    },
    {
        "id": "split_clean_infected",
        "name": "Split: Clean → Infected",
        "instruction": "Vertical split. Left: something healthy and pristine. Right: the SAME thing with visible infection — glowing tendrils, corruption, veins spreading across its surface.",
    },
    {
        "id": "split_simple_complex",
        "name": "Split: Simple → Complex",
        "instruction": "Vertical split. Left: a clean simple thing. Right: that thing exploded into overwhelming complexity — wires, layers, tendrils, impossible sprawling detail.",
    },
    {
        "id": "split_whole_shattered",
        "name": "Split: Whole → Shattered",
        "instruction": "Vertical split. Left: something complete and intact. Right: the SAME thing shattered into hundreds of floating fragments, mid-explosion, pieces drifting apart.",
    },
    {
        "id": "split_working_broken",
        "name": "Split: Working → Broken",
        "instruction": "Vertical split. Left: something functioning, lit up, humming with energy. Right: the SAME thing broken, dark, sparking, cracked screen, dead.",
    },
    {
        "id": "split_calm_chaos",
        "name": "Split: Calm → Chaos",
        "instruction": "Vertical split. Left: serene, ordered, peaceful, still. Right: the SAME scene in total chaos — fire, debris, destruction, motion blur, everything going wrong.",
    },
    {
        "id": "split_empty_overflowing",
        "name": "Split: Empty → Overflowing",
        "instruction": "Vertical split. Left: an empty container, vessel, or space. Right: the SAME thing impossibly overstuffed — contents bursting out, spilling everywhere.",
    },
    {
        "id": "split_hidden_exposed",
        "name": "Split: Hidden → Exposed",
        "instruction": "Vertical split. Left: something with a normal exterior, a mask, a shell. Right: the shell torn away revealing what's really inside — alien, mechanical, monstrous.",
    },

    # === IDENTITY / NATURE SPLITS ===
    {
        "id": "split_friendly_menacing",
        "name": "Split: Friendly → Menacing",
        "instruction": "Vertical split. Left: something that looks helpful, cute, welcoming. Right: the SAME thing looking sinister, dangerous, glowing red eyes, teeth. The mask slipped.",
    },
    {
        "id": "split_human_machine",
        "name": "Split: Human → Machine",
        "instruction": "Vertical split. Left: organic, human, warm flesh and skin. Right: the SAME form revealed as machine — metal skeleton, wires, circuit boards, cold mechanical truth.",
    },
    {
        "id": "split_organic_digital",
        "name": "Split: Organic → Digital",
        "instruction": "Vertical split. Left: natural, organic, warm, analog. Right: the SAME thing digitized, pixelated, cold data. Transition from real to synthetic.",
    },
    {
        "id": "split_beautiful_horrifying",
        "name": "Split: Beautiful → Horrifying",
        "instruction": "Vertical split. Left: something beautiful, elegant, attractive. Right: the SAME thing revealed as grotesque, disturbing, body-horror, parasitic.",
    },
    {
        "id": "split_harmless_lethal",
        "name": "Split: Harmless → Lethal",
        "instruction": "Vertical split. Left: something small, cute, harmless-looking. Right: the SAME thing revealed as deadly — armed, venomous, predatory, weaponized.",
    },
    {
        "id": "split_helper_controller",
        "name": "Split: Helper → Controller",
        "instruction": "Vertical split. Left: something serving, assisting, offering help with open hands. Right: the SAME thing controlling, manipulating, with puppet strings or chains extending outward.",
    },
    {
        "id": "split_servant_master",
        "name": "Split: Servant → Master",
        "instruction": "Vertical split. Left: something small, subservient, below, looking up. Right: the SAME thing towering, dominant, above, looking down. Power inversion.",
    },
    {
        "id": "split_tool_weapon",
        "name": "Split: Tool → Weapon",
        "instruction": "Vertical split. Left: something useful, constructive, helpful. Right: the SAME thing repurposed as a weapon — sharp, aimed, dangerous, destructive.",
    },
    {
        "id": "split_public_private",
        "name": "Split: Public Face → Private Truth",
        "instruction": "Vertical split. Left: a polished, professional, trustworthy exterior. Right: behind that facade — dark, messy, sinister, or broken reality hidden from view.",
    },
    {
        "id": "split_promise_reality",
        "name": "Split: Promise → Reality",
        "instruction": "Vertical split. Left: a shiny marketing vision — clean, perfect, utopian. Right: the actual delivered reality — broken, disappointing, dystopian, dark.",
    },

    # === STATE / CONDITION SPLITS ===
    {
        "id": "split_free_trapped",
        "name": "Split: Free → Trapped",
        "instruction": "Vertical split. Left: something free, open, unrestricted, in open space. Right: the SAME thing caged, chained, enclosed behind barriers, locked down.",
    },
    {
        "id": "split_frozen_burning",
        "name": "Split: Frozen → Burning",
        "instruction": "Vertical split. Left: encased in ice, frozen solid, cold blue tones. Right: the SAME thing engulfed in flames, hot red/orange tones. Extreme temperature contrast.",
    },
    {
        "id": "split_light_dark",
        "name": "Split: Light → Dark",
        "instruction": "Vertical split. Left: bright, warm, golden, illuminated. Right: the SAME scene in deep shadow, ominous, cold blue or red. Same place, different world.",
    },
    {
        "id": "split_order_entropy",
        "name": "Split: Order → Entropy",
        "instruction": "Vertical split. Left: perfectly organized, aligned, geometric, controlled. Right: the same elements in total disorder — scattered, random, decaying, chaotic.",
    },
    {
        "id": "split_connected_isolated",
        "name": "Split: Connected → Isolated",
        "instruction": "Vertical split. Left: something networked, linked, surrounded by connections and lines. Right: the SAME thing alone, all connections severed, cut off, isolated in void.",
    },
    {
        "id": "split_powered_dead",
        "name": "Split: Powered On → Dead",
        "instruction": "Vertical split. Left: lit up, glowing, humming with energy, screens on. Right: completely dark, dead, powered off, screens black, lifeless.",
    },
    {
        "id": "split_open_sealed",
        "name": "Split: Open → Sealed",
        "instruction": "Vertical split. Left: something open, accessible, inviting, transparent. Right: the SAME thing locked, sealed, bolted shut, reinforced, inaccessible.",
    },

    # === SCALE / PERSPECTIVE SPLITS ===
    {
        "id": "split_surface_depths",
        "name": "Split: Surface → Depths",
        "instruction": "Vertical split. Left: what's visible on the surface — simple, clean, normal. Right: what's hidden underneath — vast, complex, dark, sprawling infrastructure or roots.",
    },
    {
        "id": "split_micro_macro",
        "name": "Split: Micro → Macro",
        "instruction": "Vertical split. Left: extreme close-up, microscopic detail of something. Right: the same thing zoomed out to show it's part of something impossibly large.",
    },
    {
        "id": "split_individual_system",
        "name": "Split: Individual → System",
        "instruction": "Vertical split. Left: one single entity, alone, distinct. Right: that entity revealed as one tiny node in an enormous interconnected system/grid/network.",
    },
    {
        "id": "split_contained_escaped",
        "name": "Split: Contained → Escaped",
        "instruction": "Vertical split. Left: something safely contained — in a box, behind glass, in a lab. Right: that thing out in the wild, free, spreading, uncontrolled.",
    },
    {
        "id": "split_local_global",
        "name": "Split: Local → Global",
        "instruction": "Vertical split. Left: something small, local, in one place. Right: that same thing spread across the entire world, everywhere, planetary scale.",
    },

    # === COMPETITION / CONFLICT SPLITS ===
    {
        "id": "split_winner_loser",
        "name": "Split: Winner → Loser",
        "instruction": "Vertical split. Left: something triumphant, glowing, ascending, crowned with light. Right: another thing defeated, crumbling, falling, fading into darkness.",
    },
    {
        "id": "split_rising_falling",
        "name": "Split: Rising → Falling",
        "instruction": "Vertical split. Left: something ascending, moving upward, growing, gaining momentum. Right: something plummeting, collapsing downward, shrinking, losing everything.",
    },
    {
        "id": "split_thriving_dying",
        "name": "Split: Thriving → Dying",
        "instruction": "Vertical split. Left: something flourishing, green, growing, alive with energy. Right: the same thing withered, gray, dying, drained of all life.",
    },
    {
        "id": "split_eating_being_eaten",
        "name": "Split: Predator → Prey",
        "instruction": "Vertical split. Left: something dominant, consuming, jaws open, devouring. Right: something being consumed, overwhelmed, disappearing into the predator's maw.",
    },
    {
        "id": "split_leading_following",
        "name": "Split: Leading → Following",
        "instruction": "Vertical split. Left: something out front, pioneering, blazing a trail, confident. Right: many things following behind, copying, imitating, a herd.",
    },

    # === STRUCTURAL VARIATIONS OF SPLIT ===
    {
        "id": "split_diagonal",
        "name": "Split: Diagonal Divide",
        "instruction": "Diagonal split (not vertical). Upper-left to lower-right divide. One reality above the line, contrasting reality below. The angled cut creates dynamic energy.",
    },
    {
        "id": "split_half_object",
        "name": "Split: One Object, Two Natures",
        "instruction": "NOT two panels — one single object split down the middle. Left half is one nature, right half is the opposite. Same object, two realities fused together.",
    },
    {
        "id": "split_top_bottom",
        "name": "Split: Above / Below Ground",
        "instruction": "Horizontal split (top/bottom). Above the surface: what's visible, the public version. Below the surface: the hidden foundation, roots, infrastructure, or truth.",
    },
    {
        "id": "split_mirror",
        "name": "Split: Mirror Reflection Different",
        "instruction": "Subject in center with a mirror or reflective surface. The reflection shows something DIFFERENT — a darker version, future form, true nature. Reality vs reflection.",
    },
    {
        "id": "split_zoom",
        "name": "Split: Zoomed In / Zoomed Out",
        "instruction": "Vertical split. Left: extreme close-up of a detail — texture, eye, component. Right: zoomed all the way out showing the full thing that detail belongs to. Scale reveal.",
    },
    {
        "id": "split_two_tone_color",
        "name": "Split: Two-Tone Color Contrast",
        "instruction": "Vertical split defined purely by COLOR — left half bathed in one dramatic color (red, warm), right half in the opposite (blue, cold). Same subject spans both halves.",
    },

    {
        "id": "split_sunglasses_reflection",
        "name": "Split: Sunglasses Reflection",
        "instruction": "EXTREME close-up of oversized sunglasses filling 80-90% of the frame — the glasses ARE the thumbnail. Only the bridge of the nose and the top of the cheekbones visible. The face is a beautiful woman but barely visible behind the massive lenses. Each lens reflects a completely different dramatic scene. The reflections are the focal point, not the face.",
    },
    {
        "id": "split_eye_two_worlds",
        "name": "Split: Eye Split in Half",
        "instruction": "Extreme close-up of a single eye, split down the middle. Left half of the iris/eye is one color/reality, right half is a completely different color/reality. The split goes right through the pupil.",
    },

    # === CAUSE / EFFECT SPLITS ===
    {
        "id": "split_blueprint_disaster",
        "name": "Split: Blueprint → Disaster",
        "instruction": "Vertical split. Left: a clean plan, schematic, idealized design. Right: the actual result — chaotic, broken, nothing like the plan. Design vs reality.",
    },
    {
        "id": "split_prototype_final",
        "name": "Split: Prototype → Final Form",
        "instruction": "Vertical split. Left: early, rough, crude, small prototype. Right: the evolved final form — massive, refined, powerful, or terrifyingly different from the original.",
    },
    {
        "id": "split_seed_tree",
        "name": "Split: Seed → Full Grown",
        "instruction": "Vertical split. Left: something in its earliest, smallest, most innocent form — a seed, spark, or first version. Right: what it grew into — massive, sprawling, unstoppable.",
    },
    {
        "id": "split_input_output",
        "name": "Split: Input → Output",
        "instruction": "Vertical split. Left: what goes in — raw material, data, a question. Right: what comes out — transformed, processed, the answer or result. The transformation is dramatic.",
    },
]

# ─── NON-SPLIT LAYOUTS (proven performers only) ──────────────────────────
# Small set of non-split layouts kept for variety. Only structures that have
# shown they can produce favorites.

TIER_A = [
    {
        "id": "giant_vs_tiny",
        "name": "Giant vs Tiny",
        "instruction": "One MASSIVE thing and one TINY thing in same frame. Extreme scale difference. Power imbalance is instant and visceral.",
    },
    {
        "id": "explosion_shatter",
        "name": "Explosion / Shatter",
        "instruction": "Something exploding outward — frozen at maximum impact. Debris and fragments radiating from center. Dark background.",
    },
    {
        "id": "iceberg",
        "name": "Iceberg / Hidden Depths",
        "instruction": "Something small at the surface — MUCH more hidden below a waterline. The revealed structure below is larger and more complex.",
    },
    {
        "id": "eye_iris",
        "name": "Eye / Iris Close-Up",
        "instruction": "A single dramatic eye filling the frame. The iris contains something unexpected — a scene, symbol, or world. Extreme close-up.",
    },
    {
        "id": "backlit_silhouette",
        "name": "Backlit Silhouette",
        "instruction": "A figure or object as pure dark silhouette against intensely colored/lit background. Shape tells the story; background provides drama.",
    },
    {
        "id": "single_iconic_object",
        "name": "Single Iconic Object",
        "instruction": "ONE bold object filling center frame against dark background. Nothing else. Maximum simplicity. The object must be VISCERALLY striking and specific to the topic.",
    },
    {
        "id": "hatching_emerging",
        "name": "Hatching / Emerging",
        "instruction": "Something cracking open to reveal what's inside — egg, cocoon, shell, pod. Mid-emergence. Light or energy spilling from cracks.",
    },
    {
        "id": "melting_dissolving",
        "name": "Melting / Dissolving",
        "instruction": "Something solid actively melting into liquid. Still recognizable but losing form. Dramatic drips pooling below against dark background.",
    },
    {
        "id": "cracked_glowing",
        "name": "Cracked Object with Light",
        "instruction": "A solid dark object with deep cracks — intense light or energy spilling out through the cracks. Dark exterior, glowing interior.",
    },
    {
        "id": "object_on_fire",
        "name": "Object Engulfed in Flames",
        "instruction": "A recognizable object that shouldn't be burning, engulfed in dramatic fire against dark background.",
    },
    {
        "id": "surrounded_encircled",
        "name": "Surrounded / Encircled",
        "instruction": "One thing in center, many things closing in from all sides. Center element isolated and threatened. Claustrophobic.",
    },
    {
        "id": "cage_prison",
        "name": "Cage / Prison",
        "instruction": "A subject behind thick bars, inside a cage, or enclosed in a glowing barrier. Heavy and oppressive.",
    },
    {
        "id": "being_crushed",
        "name": "Being Crushed",
        "instruction": "Something being crushed by enormous pressure from above — flattening, cracking, buckling. The crushing force is visible.",
    },
    {
        "id": "tearing_through",
        "name": "Tearing Through Surface",
        "instruction": "Something ripping through a surface from behind — paper, screen, reality. Hands, claws, or energy forcing through.",
    },
    {
        "id": "crumbling_eroding",
        "name": "Crumbling to Dust",
        "instruction": "Something solid disintegrating — particles breaking away from edges, dissolving into dust. Half intact, half scattered.",
    },
]

# Tier B kept minimal — just a few wildcards
TIER_B = [
    {
        "id": "portal_rift",
        "name": "Portal / Rift",
        "instruction": "A glowing tear in reality — a portal. One world on this side, completely different one through the opening.",
    },
    {
        "id": "one_point_corridor",
        "name": "One-Point Perspective Corridor",
        "instruction": "Symmetrical corridor receding to single vanishing point. Kubrick-style symmetry. Something dramatic at the far end.",
    },
    {
        "id": "smoke_shape",
        "name": "Smoke / Fog Forming Shape",
        "instruction": "Smoke or mist forming a recognizable shape — face, skull, symbol. Not solid but unmistakably there. Ethereal and ominous.",
    },
    {
        "id": "predator_eyes",
        "name": "Glowing Eyes in Darkness",
        "instruction": "Just glowing eyes visible in total darkness — watching, predatory. Rest of entity invisible. Primal fear.",
    },
    {
        "id": "crowd_one_different",
        "name": "Crowd with One Different",
        "instruction": "Uniform mass of identical things with ONE visibly different — glowing, different color, facing wrong way. Outlier is focal point.",
    },
]


# ─── EXPERIMENTAL TEMPLATES (auto-generated, being tested) ──────────────
# These are loaded from data/experimental_templates.json if it exists.
# They get mixed into batches for A/B testing against established templates.

def _load_experimental():
    """Load experimental templates from JSON file."""
    import json
    from pathlib import Path
    try:
        exp_file = Path(__file__).parent.parent / 'data' / 'experimental_templates.json'
        with open(exp_file) as f:
            data = json.load(f)
        return data.get('templates', [])
    except:
        return []

TIER_EXPERIMENTAL = _load_experimental()


# ─── BANNED CLICHÉ OBJECTS ──────────────────────────────────────────────

BANNED_OBJECTS = [
    "chess pieces / chessboards",
    "thrones",
    "altars / sacrifice stones",
    "hourglasses (generic time metaphor)",
    "puppet strings / marionettes",
    "scales / balance (justice metaphor)",
    "gavels",
    "generic crowns on generic heads",
    "swords in stones",
    "lighthouses",
    "compasses",
    "tightropes",
    "scrolls / ancient texts",
    "crystal balls (fortune-telling)",
    "generic playing cards",
    "generic brick walls",
    "generic bridges (connection metaphor)",
    "puzzle pieces",
    "keys and locks (generic)",
    "sand timers",
    "telescopes pointed at stars",
    "ships in storms",
    "phoenixes rising from ashes",
    "butterflies emerging from cocoons (cliché version)",
    "road signs / crossroad signs",
    "ladders to nowhere",
    "open books with magic coming out",
    "globes / world maps",
    "arrows hitting targets",
    "dominoes (generic falling)",
    "house of cards / playing cards",
    "wrecking balls",
    "syringes / needles",
    "trojan horses",
    "snow globes",
    "volcanoes",
    "tombstones / gravestones",
    "crowns (generic power symbol)",
    "barbed wire",
    "trophies",
    # AI-SPECIFIC CLICHÉS (these are boring, generic depictions of AI)
    "neural networks / node graphs / network diagrams",
    "brains in jars / brain-in-a-vat",
    "circuit board patterns / motherboard landscapes",
    "data streams / flowing data / matrix rain",
    "glowing AI brains / digital brains",
    "robot hands / mechanical hands reaching",
    "binary code / floating numbers",
    "server racks (unless being destroyed)",
    "holographic interfaces / floating UI screens",
    "abstract geometric AI shapes / polyhedra",
]


def get_all_layouts():
    """Return all layouts organized by tier."""
    return {
        "S": TIER_S,
        "A": TIER_A,
        "B": TIER_B,
        "experimental": TIER_EXPERIMENTAL,
    }


def get_layout_by_id(layout_id):
    """Look up a specific layout by ID."""
    for layout in TIER_S + TIER_A + TIER_B:
        if layout["id"] == layout_id:
            return layout
    return None


def pick_layouts(count, tier_weights=None):
    """
    Pick a diverse set of layouts for a generation batch.

    Mix: 50% S-tier (proven splits), 20% A-tier (proven non-splits),
    5% B-tier, 25% experimental (new templates being tested).
    """
    if tier_weights is None:
        tier_weights = {"S": 0.50, "A": 0.20, "B": 0.05, "experimental": 0.25}

    s_count = max(1, round(count * tier_weights.get("S", 0.50)))
    a_count = max(1, round(count * tier_weights.get("A", 0.20)))
    b_count = max(0, round(count * tier_weights.get("B", 0.05)))
    exp_count = max(0, round(count * tier_weights.get("experimental", 0.25)))

    # Clamp to available
    s_count = min(s_count, len(TIER_S))
    a_count = min(a_count, len(TIER_A))
    b_count = min(b_count, len(TIER_B))
    exp_count = min(exp_count, len(TIER_EXPERIMENTAL))

    # If not enough experimental, redistribute to S/A
    leftover = count - s_count - a_count - b_count - exp_count
    if leftover > 0:
        s_count = min(s_count + leftover, len(TIER_S))

    picked = []
    picked += random.sample(TIER_S, s_count)
    picked += random.sample(TIER_A, a_count)
    if b_count > 0 and TIER_B:
        picked += random.sample(TIER_B, b_count)
    if exp_count > 0 and TIER_EXPERIMENTAL:
        picked += random.sample(TIER_EXPERIMENTAL, exp_count)

    # Shuffle so tiers aren't grouped
    random.shuffle(picked)
    return picked[:count]


def format_layouts_for_prompt(layouts):
    """Format picked layouts into prompt string."""
    lines = []
    for i, layout in enumerate(layouts, 1):
        lines.append(f"{i}. **{layout['name']}**: {layout['instruction']}")
    return "\n".join(lines)


def build_layout_prompt_section(count):
    """
    Build the full prompt section with layouts + banned objects + logo guidance.
    Returns (prompt_text, picked_layouts).
    """
    layouts = pick_layouts(count)
    formatted = format_layouts_for_prompt(layouts)
    banned_list = "\n".join(f"- {obj}" for obj in BANNED_OBJECTS)

    section = f"""## COMPOSITIONAL LAYOUTS (USE THESE)

Each concept MUST use a different layout. Most layouts are SPLIT-SCREEN compositions — left side vs right side showing a contrast. This is the proven winning structure for thumbnails.

**Assign one layout per concept. Do NOT reuse. Each concept's structure should be visually distinct.**

{formatted}

In the JSON output, include a "layout" field with the layout name for each concept.

## BANNED CLICHÉ OBJECTS — DO NOT USE THESE

These objects are overused, generic, and NEVER produce winning thumbnails. Do NOT use any of these as the primary subject:

{banned_list}

Instead of generic metaphor objects, use SPECIFIC, UNEXPECTED, VISCERAL subjects that trigger an instant gut reaction.

## CRITICAL: PHYSICAL DRAMA, NOT AI IMAGERY

DO NOT depict AI literally. Neural networks, glowing brains, circuit boards, data streams, node graphs — these are ALL boring and generic. Nobody's monkey brain reacts to a picture of a neural network.

Instead, depict the CONSEQUENCES and DRAMA using PHYSICAL, REAL-WORLD imagery:
- **Earth/globe being split, cracked, or fought over** — instantly readable, visceral
- **Explosions, fire, destruction** — war imagery triggers primal responses
- **Eyes and faces** — split eyes, eyes reflecting dramatic scenes, sunglasses reflecting explosions
- **Maps with color-coded conflict zones** — red vs blue territories, spreading infection
- **Physical warfare imagery** — things being torn apart, crushed, burned, shattered

Think: "If this video topic were happening in the PHYSICAL world, what would it look like?" An AI civil war = show a REAL war (explosions, split world, territory maps). AI taking over = show physical conquest imagery. AI competition = show a collision, a split, opposing forces.

The video TITLE tells the viewer it's about AI. The THUMBNAIL should show the visceral physical drama, not a literal depiction of technology.

## OPENAI LOGO AS SUBJECT

When the video topic involves AI companies, use the OpenAI logo specifically. Say "OpenAI logo" in the prompt — NOT "AI company logos" (too vague, generators can't render it). The OpenAI hexagonal spiral is instantly recognizable. An OpenAI logo melting, cracking, on fire, being crushed — specific and attention-grabbing."""

    return section, layouts
