"""Generate the README banner (docs/banner.svg).

Usage: python docs/banner_gen.py

Design direction: the wordmark is the hero, no concept play. There is exactly
one colored element in the whole image — the gradient line under the wordmark,
using the same brand palette as the admin panel (#4285F4 → #9B72CB → #D96570),
which in the panel itself also appears in exactly one place (the block-line
track).

Both constraints come from how GitHub renders it (SVGs in a README are
rendered as images):
- No filters/shadows — a blurred glow just turns to mud at small sizes
- Fonts use the system monospace stack, no external fonts (the <img> sandbox
  blocks external links)
"""
import io
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "docs", "banner.svg")

W, H = 1280, 260
MONO = "ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace"
CHIPS = ["no account", "no API key", "single Go binary", "admin panel"]

cx = W / 2
p = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" role="img" '
    f'aria-label="gemini-web2api-go — the Gemini web protocol, spoken as OpenAI">',
    '<defs><linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0">'
    '<stop offset="0" stop-color="#4285F4"/>'
    '<stop offset="0.55" stop-color="#9B72CB"/>'
    '<stop offset="1" stop-color="#D96570"/></linearGradient></defs>',
    f'<rect width="{W}" height="{H}" fill="#0D1117"/>',
    f'<text x="{cx}" y="112" font-family="{MONO}" font-size="46" font-weight="600" '
    f'letter-spacing="-1.2" fill="#E9EEF6" text-anchor="middle">gemini-web2api-go</text>',
    f'<rect x="{cx - 190}" y="136" width="380" height="2.5" rx="1.25" fill="url(#sweep)"/>',
    f'<text x="{cx}" y="174" font-family="{MONO}" font-size="15" fill="#8695AE" '
    f'text-anchor="middle">gemini.google.com &#8594; OpenAI-compatible /v1</text>',
]

# One row of chips, laid out and centered by hand (SVG has no flex)
FW, PAD, GAP = 7.1, 15, 11        # FW = approximate advance width of a 12px monospace char
widths = [len(c) * FW + PAD * 2 for c in CHIPS]
x = cx - (sum(widths) + GAP * (len(CHIPS) - 1)) / 2
for c, w in zip(CHIPS, widths):
    p.append(f'<rect x="{x:.1f}" y="200" width="{w:.1f}" height="27" rx="13.5" '
             f'fill="#161C26" stroke="#242C3A"/>')
    p.append(f'<text x="{x + w / 2:.1f}" y="218" font-family="{MONO}" font-size="12" '
             f'fill="#7D8CA6" text-anchor="middle">{c}</text>')
    x += w + GAP

p.append("</svg>")
io.open(OUT, "w", encoding="utf-8").write("\n".join(p))
print(f"wrote {OUT}  ({os.path.getsize(OUT)} bytes)")