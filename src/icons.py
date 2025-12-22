# icons.py

DEFAULT_ENTITY_ICON = "mdi:radio-tower"

ICON_KEYWORDS = [
    ("garage", "mdi:garage"),
    ("door", "mdi:door"),
    ("gate", "mdi:gate"),
    ("lock", "mdi:lock"),
    ("unlock", "mdi:lock-open-variant"),
    ("alarm", "mdi:alarm-light"),
    ("light", "mdi:lightbulb"),
    ("fan", "mdi:fan"),
    ("sprink", "mdi:sprinkler"),
    ("water", "mdi:water"),
    ("heat", "mdi:fire"),
    ("ac", "mdi:snowflake"),
    ("car", "mdi:car"),
    ("outlet", "mdi:power-socket-us"),
    ("plug", "mdi:power-plug"),
    ("bell", "mdi:bell"),
    ("remote", "mdi:remote"),
    ("rf", "mdi:radio-tower"),
    ("radio", "mdi:radio-tower"),
]

ICON_BY_EXTENSION = {
    ".sub": "mdi:remote",
    ".rfcat.json": "mdi:radio-tower",
}

def guess_icon_from_text(text: str):
    t = (text or "").lower()
    for kw, icon in ICON_KEYWORDS:
        if kw in t:
            return icon
    return None
