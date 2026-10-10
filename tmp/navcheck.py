import base64
import json
import subprocess
import sys
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
PROFILE = r"A:\code\django\me3ulandsang\tmp\chrome-profile"

UA_PIXEL = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 9 Pro) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
)

DEVICES = {
    "pixel9pro": (427, 952, 2.625, True, UA_PIXEL),
    "pixel8_responsive": (412, 915, 1.0, False, None),
    "galaxy_a55": (384, 832, 2.75, True, "Mozilla/5.0 (Linux; Android 14; SM-A556B) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"),
}

PROBE = r"""
(() => {
  const nav = document.querySelector('.mobile-nav');
  const cs = getComputedStyle(nav);
  const r = nav.getBoundingClientRect();
  const vp = window.visualViewport;
  const offsetVar = getComputedStyle(document.documentElement)
      .getPropertyValue('--mobile-nav-viewport-offset');
  const hit = document.elementFromPoint(Math.round(r.left + r.width/2),
                                        Math.round(r.top + r.height/2));
  const stylesheetHref = [...document.styleSheets].map(s => {
      try { return s.href || '(inline)'; } catch(e){ return '(blocked)'; }
  });
  const body = document.body;
  return JSON.stringify({
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    deviceWidth: screen.width,
    devicePixelRatio: window.devicePixelRatio,
    visualViewport: vp ? {height: vp.height, offsetTop: vp.offsetTop, scale: vp.scale} : null,
    offsetVar: offsetVar,
    mediaQueries: {
      maxWidth860: matchMedia('(max-width:860px)').matches,
      coarse: matchMedia('(hover:none) and (pointer:coarse)').matches,
      anyPointerCoarse: matchMedia('(pointer:coarse)').matches,
    },
    nav: {
      display: cs.display,
      position: cs.position,
      bottom: cs.bottom,
      top: cs.top,
      left: cs.left,
      right: cs.right,
      zIndex: cs.zIndex,
      rect: {x: r.x, y: r.y, w: r.width, h: r.height},
      visibleInViewport: r.top < window.innerHeight && r.bottom > 0 && r.width > 0,
      hitTarget: hit ? (hit.className || hit.tagName) : null,
    },
    bodyPaddingBottom: getComputedStyle(body).paddingBottom,
    bodyScroll: {w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight},
    stylesheets: stylesheetHref,
    navParent: nav.parentElement.tagName + '.' + nav.parentElement.className,
    navHTMLlen: nav.outerHTML.length,
    itemCount: nav.querySelectorAll('.mobile-nav__item').length,
  });
})()
"""


def http_json(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}") as resp:
        return json.loads(resp.read().decode())


def main():
    proc = subprocess.Popen([
        CHROME,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        for _ in range(60):
            try:
                http_json("/json/version")
                break
            except Exception:
                time.sleep(0.25)
        else:
            print("chrome never came up")
            return 1

        pages = [p for p in http_json("/json/list") if p["type"] == "page"]
        version = http_json("/json/version")
        print("browser:", version.get("Browser"))
        ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"],
                                         suppress_origin=True, timeout=30)
        msg_id = 0

        def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                data = json.loads(ws.recv())
                if data.get("id") == msg_id:
                    return data

        send("Page.enable")
        send("Runtime.enable")

        url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"
        only = sys.argv[2] if len(sys.argv) > 2 else None

        for name, (w, h, dpr, mobile, ua) in DEVICES.items():
            if only and only != name:
                continue
            send("Emulation.setDeviceMetricsOverride", {
                "width": w, "height": h, "deviceScaleFactor": dpr, "mobile": mobile,
            })
            send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
            if ua:
                send("Emulation.setUserAgentOverride", {"userAgent": ua})
            else:
                send("Emulation.setUserAgentOverride", {"userAgent": ""})
            send("Page.navigate", {"url": url})
            time.sleep(3.0)

            res = send("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})
            raw = res["result"]["result"].get("value")
            print("=" * 70)
            print(f"DEVICE: {name}  ({w}x{h} @{dpr}x mobile={mobile})")
            if raw is None:
                print("  probe failed:", json.dumps(res)[:600])
                continue
            data = json.loads(raw)
            print(json.dumps(data, indent=2))

            shot = send("Page.captureScreenshot", {"format": "png"})
            out = rf"A:\code\django\me3ulandsang\tmp\shot-{name}.png"
            with open(out, "wb") as fh:
                fh.write(base64.b64decode(shot["result"]["data"]))
            print("screenshot:", out)

        ws.close()
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
