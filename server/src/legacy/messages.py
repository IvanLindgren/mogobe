"""Allow only actions present in the shipped original ControlPanel SWF.

WalkableScreen invokes avatar methods dynamically; arbitrary method names,
speaker IDs, animation class names and malformed targets must never pass.
"""

import math
from pathlib import Path
from xml.etree import ElementTree

# The original menu sends closeChat__<id>; clients resolve that ID through
# their bundled Russian chat XML. Allow only phrases shipped in that same file.
CHAT_PHRASES = {
    node.attrib["id"]: node.attrib["txt"]
    for node in ElementTree.parse(
        Path(__file__).resolve().parents[3] / "assets/original/Xmls/lang/chat_5.xml"
    ).iter()
    if node.get("id") and node.get("txt")
}

EMOTIONS = {"Ico_mad", "Ico_sad", "Ico_stupid", "Ico_wink", "Ico_laughing"}
AVATAR_EFFECTS = {
    "Ico_bubbles",
    "Ico_hearts",
    "Ico_heart",
    "Ico_rain",
    "Ico_snow",
    "Ico_milk",
    "Ico_Snowball",
    "Ico_Flowers",
}
ROOM_EFFECTS = {"Ico_teeth1", "Ico_teeth2", "Ico_Fireworks"}


def validated_message(text, sender, members):
    parts = text.split("__")
    action = parts[0]
    if action in {"speak", "speakRoom", "speakServer"}:
        content = text.partition("__")[2]
        # Command arguments can contain valid double underscores in a nickname
        # or announcement. These commands are consumed by the server, not speech.
        if not content.lstrip().casefold().startswith(("/give ", "/alert ")):
            while "__" in content:
                content = content.replace("__", "_")
        content = content.strip()
        if not content or len(content) > 240 or any(ord(c) < 32 for c in content):
            return None
        return action + "__" + content
    if action == "closeChat" and len(parts) == 2 and parts[1] in CHAT_PHRASES:
        return text
    if action == "emoticons" and len(parts) == 2 and parts[1] in EMOTIONS:
        return text
    if action == "effect" and len(parts) >= 3:
        if parts[1] in AVATAR_EFFECTS and len(parts) == 3:
            if parts[2].isdecimal() and int(parts[2]) in members:
                return "__".join(parts[:2] + [str(int(parts[2]))])
        elif parts[1] in ROOM_EFFECTS and len(parts) == 5:
            try:
                x, y = map(float, parts[3].split(":"))
            except ValueError:
                return None
            if (
                math.isfinite(x)
                and math.isfinite(y)
                and 0 <= x < 768
                and 0 <= y < 480
                and parts[4] == "false"
            ):
                # The source avatar always belongs to the authenticated sender.
                return f"effect__{parts[1]}__{sender}__{x:g}:{y:g}__false"
    # Bare text from SmartFox clients is still treated as speech; an unknown
    # explicit protocol command is rejected rather than displayed as garbage.
    if len(parts) == 1:
        return validated_message("speak__" + text, sender, members)
    return None
