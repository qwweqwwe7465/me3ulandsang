import sys
from PIL import Image

for path in sys.argv[1:]:
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    print(f"{path}  {w}x{h}")

    for label, y in (("top", 40), ("mid", h // 2), ("bottom-30", h - 30),
                     ("bottom-70", h - 70), ("bottom-120", h - 120)):
        y = max(0, min(h - 1, y))
        row = [px[x, y] for x in range(0, w, max(1, w // 12))]
        avg = tuple(sum(c[i] for c in row) // len(row) for i in range(3))
        print(f"  y={y:>5} ({label:>11}) avg={avg}")

    # Scan the bottom region for a horizontal band whose luminance differs from
    # the row above it -- i.e. a dock sitting over the page.
    def rowluma(y):
        return sum(sum(px[x, y]) for x in range(0, w, 4)) / (3 * len(range(0, w, 4)))

    print("  luma profile (bottom 140px):")
    prev = None
    for y in range(h - 140, h, 10):
        cur = rowluma(y)
        delta = "" if prev is None else f"  d={cur - prev:+.1f}"
        print(f"    y={y:>5} luma={cur:6.1f}{delta}")
        prev = cur
