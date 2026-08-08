"""Platform detection + install instructions.

This is intentionally simple and data-driven so anyone can tweak the installer
without touching route logic: edit the ``PLATFORMS`` list below (add a step,
change a button, add a platform) and the /install page updates automatically.

Each platform is a dict:
    id       short key, also used to auto-highlight the visitor's platform
    name     human label shown on the card
    icon     key mapped to an inline SVG in templates/install.html
    tagline  one-line summary under the name
    cta      the primary button: {"type": ..., "label": ..., "href": ...}
             type is one of:
               "download" - a normal link (e.g. the APK)
               "pwa"      - triggers the browser's "Install app" prompt (JS),
                            with a manual fallback shown automatically
               "manual"   - no button; the steps ARE the instructions (iOS)
    steps    ordered list of short instructions (basic HTML allowed)
    note     optional small print under the steps
"""
from __future__ import annotations

# One place to change where the native app is published.
RELEASES_URL = "https://github.com/kiingniick/SprintGPT/releases/latest"
# Every release uploads a fixed-name copy of the APK, so this always points at the
# newest build straight from the repo (no version number to keep in sync here).
APK_URL = "https://github.com/kiingniick/SprintGPT/releases/latest/download/SprintGPT.apk"


def detect_platform(user_agent: str) -> str:
    """Best-effort platform guess from a User-Agent string.

    Returns one of: android, ios, windows, macos, linux, unknown.
    The homepage refines this in the browser (where more signals exist), so a
    rough guess here is fine — it just avoids a flash of the wrong content.
    """
    ua = (user_agent or "").lower()
    if "android" in ua:
        return "android"
    if any(k in ua for k in ("iphone", "ipad", "ipod")):
        return "ios"
    if "windows" in ua:
        return "windows"
    if "mac os x" in ua or "macintosh" in ua:
        return "macos"
    if "linux" in ua:
        return "linux"
    return "unknown"


PLATFORMS = [
    {
        "id": "android",
        "name": "Android",
        "icon": "android",
        "tagline": "Install the native app (works offline or online)",
        "cta": {"type": "download", "label": "Download the app (.apk)", "href": APK_URL},
        "steps": [
            "Tap <strong>Download the app</strong> above and open the "
            "<code>SprintGPT-*.apk</code> file.",
            "If asked, allow <strong>Install from unknown sources</strong> for your "
            "browser or Files app, then confirm the install.",
            "Open <strong>Paceloop</strong> and choose <strong>Connect to a "
            "server</strong> (already filled in) or run it fully on your phone.",
        ],
        "note": "The app checks for updates on launch and reminds you when a newer "
                "version is available. Prefer no install? Use “Add to Home Screen” instead.",
    },
    {
        "id": "ios",
        "name": "iPhone &amp; iPad",
        "icon": "apple",
        "tagline": "Add to your Home Screen (no App Store needed)",
        "cta": {"type": "manual", "label": "", "href": ""},
        "steps": [
            "Open this site in <strong>Safari</strong>.",
            "Tap the <strong>Share</strong> button "
            "(the square with an up arrow).",
            "Choose <strong>Add to Home Screen</strong>, then <strong>Add</strong>.",
            "Launch Paceloop from the new icon — it opens full-screen like an app.",
        ],
        "note": "iOS only allows Home-Screen install from Safari, not Chrome.",
    },
    {
        "id": "windows",
        "name": "Windows",
        "icon": "windows",
        "tagline": "Install as a desktop app in one click",
        "cta": {"type": "pwa", "label": "Install app", "href": ""},
        "steps": [
            "Click <strong>Install app</strong> above "
            "(Chrome or Edge).",
            "Or use the <strong>install icon</strong> in the address bar, then "
            "<strong>Install</strong>.",
            "Paceloop opens in its own window and pins to your Start menu / taskbar.",
        ],
        "note": "No button? Your browser may not support installs — just bookmark this page.",
    },
    {
        "id": "macos",
        "name": "macOS",
        "icon": "apple",
        "tagline": "Install as a Mac app in one click",
        "cta": {"type": "pwa", "label": "Install app", "href": ""},
        "steps": [
            "Click <strong>Install app</strong> above "
            "(Chrome or Edge).",
            "In Safari, use <strong>File → Add to Dock</strong> instead.",
            "Paceloop opens in its own window, ready in your Dock.",
        ],
        "note": None,
    },
    {
        "id": "linux",
        "name": "Linux",
        "icon": "linux",
        "tagline": "Install as an app in one click",
        "cta": {"type": "pwa", "label": "Install app", "href": ""},
        "steps": [
            "Click <strong>Install app</strong> above "
            "(Chrome, Chromium, or Edge).",
            "Or use your browser's <strong>Install app</strong> menu option.",
            "Paceloop gets its own launcher and window.",
        ],
        "note": None,
    },
]
