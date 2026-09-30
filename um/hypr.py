"""Linux + Hyprland backend for `um win`: native games and Proton games (XWayland), same commands.

    um win setup                                  # check grim, gpu-screen-recorder, hyprctl, /dev/uinput
    um win ps [name]                              # windows: pid, exe, title (Hyprland clients)
    um win kill <pid>                             # by exact PID only
    um win launch --steam 1623730                 # or: um win launch ./game.x86_64 -- -windowed
    um win shot --exe Palworld out.png --scale 0.33          # one window, even covered or on another workspace
    um win drive --proc Palworld "focus" "click 640 360" "key 0x1B"   # same protocol as WinDrive
    um win record --exe Palworld --out ~/caps/take1 --seconds 30      # NVENC video + only the game's audio
    um win reg get "HKCU\\Software\\Foo" --appid 1623730              # registry inside the game's Proton prefix

Windows are matched by exe name (Proton exes too, e.g. Palworld-Win64-Shipping.exe), title or Hyprland class
(Proton games are steam_app_<appid>). Screenshots use grim's toplevel capture, so the window can be covered.
Recording captures the window's screen region (keep it visible) and muxes the game's own PipeWire stream, so
the .mkv already has audio: skip `um video mux`. Input goes through a virtual uinput device (needs rw on
/dev/uinput) and is only sent while the game is the active window, like WinDrive.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

from um.common import die

# --------------------------------------------------------------------------- hyprland


def available() -> bool:
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and shutil.which("hyprctl") is not None


def hyprctl(*args: str, json_out: bool = True):
    r = subprocess.run(["hyprctl", *(["-j"] if json_out else []), *args], capture_output=True, text=True, timeout=10)
    if r.returncode:
        die(f"hyprctl {' '.join(args)} failed: {r.stderr.strip()}")
    return json.loads(r.stdout) if json_out else r.stdout.strip()


def lua() -> bool:
    """Hyprland 0.55+ with a Lua config takes hl.dsp.* calls in `hyprctl dispatch`."""
    cache = lua.__dict__
    if "v" not in cache:
        r = subprocess.run(["hyprctl", "repl", "return 1"], capture_output=True, text=True, timeout=10)
        cache["v"] = r.returncode == 0 and r.stdout.strip() == "1"
    return cache["v"]


def dispatch(legacy: list[str], lua_call: str) -> str:
    out = hyprctl("dispatch", lua_call, json_out=False) if lua() else hyprctl("dispatch", *legacy, json_out=False)
    if out.lower().startswith("error"):
        die(f"hyprctl dispatch failed: {out}")
    return out


def focus_window(addr: str):
    dispatch(["focuswindow", f"address:{addr}"], f'hl.dsp.focus({{ window = "address:{addr}" }})')


def move_cursor(x: int, y: int):
    dispatch(["movecursor", str(x), str(y)], f"hl.dsp.cursor.move({{ x = {x}, y = {y} }})")


def resize_window(addr: str, w: int, h: int):
    dispatch(["setfloating", f"address:{addr}"], f'hl.dsp.window.float({{ action = "enable", window = "address:{addr}" }})')
    dispatch(["resizewindowpixel", f"exact {w} {h},address:{addr}"],
             f'hl.dsp.window.resize({{ x = {w}, y = {h}, window = "address:{addr}" }})')


def exe_name(pid: int) -> str:
    """Wine/Proton processes keep the Windows path in argv[0]; native ones don't."""
    try:
        argv0 = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0].decode(errors="replace")
    except OSError:
        return ""
    name = re.split(r"[\\/]", argv0)[-1]
    if name.lower().endswith(".exe") or not name:
        return name
    try:
        return Path(os.readlink(f"/proc/{pid}/exe")).name
    except OSError:
        return name


def clients() -> list[dict]:
    out = []
    for c in hyprctl("clients"):
        if c.get("mapped") and c.get("pid", -1) > 0:
            out.append(dict(c, exe=exe_name(c["pid"])))
    return out


def find_window(exe=None, title=None, cls=None) -> dict:
    if not (exe or title or cls):
        die("give --exe, --title or --class")
    for c in clients():
        if exe:
            stem = exe[:-4] if exe.lower().endswith(".exe") else exe
            if not re.search(stem, c["exe"], re.I):
                continue
        if title and not re.search(title, c["title"], re.I):
            continue
        if cls and not re.search(cls, c["class"], re.I):
            continue
        return c
    die(f"no window matches exe={exe!r} title={title!r} class={cls!r} (see `um win ps`)")


def processes(name: str | None = None) -> list[dict]:
    return [dict(Id=c["pid"], ProcessName=c["exe"], MainWindowTitle=c["title"], Class=c["class"], Address=c["address"])
            for c in clients() if not name or re.search(name, c["exe"], re.I)]


def kill(pid: int):
    """SIGTERM, then SIGKILL after 5 s. Exact PID only."""
    pid = int(pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"no process {pid}")
        return
    for _ in range(50):
        time.sleep(0.1)
        if not Path(f"/proc/{pid}").exists():
            print(f"terminated {pid}")
            return
    os.kill(pid, signal.SIGKILL)
    print(f"killed {pid}")


def launch(target: str, args: list[str], steam: bool = False):
    if steam:
        url = f"steam://rungameid/{target}" if not args else f"steam://run/{target}//{' '.join(args)}/"
        cmd = ["steam", url] if shutil.which("steam") else ["xdg-open", url]
    elif target.lower().endswith(".exe"):
        die("a Windows exe on Linux: add it to Steam as a non-Steam game with Proton and launch with --steam <appid>")
    else:
        cmd = [target, *args]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def setup(args=None):
    checks = [
        ("hyprctl", available(), "run inside a Hyprland session"),
        ("grim (-T toplevel capture)", shutil.which("grim") is not None, "pacman -S grim  (1.5+)"),
        ("gpu-screen-recorder", shutil.which("gpu-screen-recorder") is not None, "pacman -S gpu-screen-recorder"),
        ("pw-dump (game-only audio)", shutil.which("pw-dump") is not None, "pacman -S pipewire"),
        ("/dev/uinput rw (input)", os.access("/dev/uinput", os.R_OK | os.W_OK),
         "grant it with a udev rule: KERNEL==\"uinput\", TAG+=\"uaccess\" (then re-login)"),
    ]
    bad = 0
    for name, ok, fix in checks:
        print(f"{'ok  ' if ok else 'MISSING'}  {name}" + ("" if ok else f"  -> {fix}"))
        bad += not ok
    if bad:
        sys.exit(1)


# --------------------------------------------------------------------------- capture


def shot(out: str, exe=None, title=None, cls=None, scale: float | None = None, timeout=20) -> str:
    c = find_window(exe, title, cls)
    dst = Path(out).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["grim", "-T", str(c.get("stableId", "")), str(dst)], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        # older Hyprland without stableId: grab the on-screen region instead
        (x, y), (w, h) = c["at"], c["size"]
        r = subprocess.run(["grim", "-g", f"{x},{y} {w}x{h}", str(dst)], capture_output=True, text=True, timeout=timeout)
    if r.returncode or not dst.exists():
        die(f"capture failed: {r.stderr.strip()[-800:]}")
    if scale:
        from PIL import Image
        im = Image.open(dst)
        small = dst.with_name(dst.stem + "_small.png")
        im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS).save(small)
        print(small)
    return str(dst)


def audio_app(pid: int) -> str | None:
    """PipeWire application.name of the game's output stream (by pid, then by the process tree)."""
    try:
        nodes = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=10).stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    # the pid lives on the node, or only on its client object
    client_pid = {}
    for n in nodes:
        p = (n.get("info") or {}).get("props") or {}
        if n.get("type", "").endswith(":Client"):
            pid = p.get("application.process.id") or p.get("pipewire.sec.pid")
            if pid:
                client_pid[n["id"]] = int(pid)
    streams = {}
    for n in nodes:
        p = (n.get("info") or {}).get("props") or {}
        if p.get("media.class") != "Stream/Output/Audio":
            continue
        pid = p.get("application.process.id") or client_pid.get(p.get("client.id"))
        if pid:
            streams[int(pid)] = p.get("application.name") or p.get("node.name")
    ppid = {}
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                ppid[int(d.name)] = int((d / "stat").read_text().rsplit(")", 1)[1].split()[1])
            except (OSError, IndexError, ValueError):
                pass
    for spid, name in streams.items():
        p = spid
        while p > 1:
            if p == pid:
                return name
            p = ppid.get(p, 1)
    # wine may play from a sibling process: fall back to anything under the same parent
    parent = ppid.get(pid)
    for spid, name in streams.items():
        if ppid.get(spid) == parent:
            return name
    return None


class Recorder:
    """gpu-screen-recorder on the window's region + the game's own audio stream -> <out>.mkv (+ .json)."""

    def __init__(self, exe=None, out="take", title=None, cls=None, fps=30, audio=True, crop=None, **_):
        self.exe, self.title, self.cls, self.fps, self.audio_on, self.crop = exe, title, cls, fps, audio, crop
        self.base = str(Path(out).expanduser().resolve())
        self.proc = None

    def start(self):
        c = find_window(self.exe, self.title, self.cls)
        (x, y), (w, h) = c["at"], c["size"]
        if self.crop:
            l, t, r, b = self.crop
            x, y, w, h = x + l, y + t, w - l - r, h - t - b
        w, h = w // 2 * 2, h // 2 * 2
        cmd = ["gpu-screen-recorder", "-w", "region", "-region", f"{w}x{h}+{x}+{y}", "-f", str(self.fps),
               "-k", "h264", "-q", "very_high", "-c", "mkv", "-cursor", "no", "-o", self.base + ".mkv"]
        self.app = audio_app(c["pid"]) if self.audio_on else None
        if self.audio_on and not self.app:
            print("no PipeWire stream for the game yet (is it playing sound?); recording video only", file=sys.stderr)
        if self.app:
            cmd[1:1] = ["-a", f"app:{self.app}"]
        Path(self.base).parent.mkdir(parents=True, exist_ok=True)
        self.log = Path(self.base + ".gsr.log")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=open(self.log, "w"), stderr=subprocess.STDOUT)
        time.sleep(1)
        if self.proc.poll() is not None:
            die(f"gpu-screen-recorder exited: {self.log.read_text(errors='replace')[-600:]}")
        return self

    def stop(self):
        if self.proc:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        meta = dict(video=self.base + ".mkv", audio="muxed" if self.app else None, audio_app=self.app)
        Path(self.base + ".json").write_text(json.dumps(meta, indent=1))
        print("recorded", self.base + ".mkv", "(+ game audio)" if self.app else "")
        return meta


# --------------------------------------------------------------------------- input (uinput)

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
REL_X, REL_Y, REL_WHEEL = 0, 1, 8
BTN_LEFT, BTN_RIGHT = 0x110, 0x111
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = 0x40045564, 0x40045565, 0x40045566
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
SHIFT = 42

# Windows virtual-key -> evdev keycode, so skills written for WinDrive keep working
VK = {0x08: 14, 0x09: 15, 0x0D: 28, 0x10: 42, 0x11: 29, 0x12: 56, 0x13: 119, 0x14: 58, 0x1B: 1, 0x20: 57,
      0x21: 104, 0x22: 109, 0x23: 107, 0x24: 102, 0x25: 105, 0x26: 103, 0x27: 106, 0x28: 108, 0x2D: 110, 0x2E: 111,
      0xA0: 42, 0xA1: 54, 0xA2: 29, 0xA3: 97, 0xA4: 56, 0xA5: 100, 0xBA: 39, 0xBB: 13, 0xBC: 51, 0xBD: 12, 0xBE: 52,
      0xBF: 53, 0xC0: 41, 0xDB: 26, 0xDC: 43, 0xDD: 27, 0xDE: 40}
VK.update({0x30 + i: c for i, c in enumerate([11, 2, 3, 4, 5, 6, 7, 8, 9, 10])})
VK.update({0x41 + i: c for i, c in enumerate([30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44])})
VK.update({0x70 + i: c for i, c in enumerate([59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88])})
VK.update({0x60 + i: c for i, c in enumerate([82, 79, 80, 81, 75, 76, 77, 71, 72, 73])})
NAMES = {"esc": 1, "escape": 1, "enter": 28, "return": 28, "space": 57, "tab": 15, "backspace": 14, "shift": 42,
         "ctrl": 29, "alt": 56, "up": 103, "down": 108, "left": 105, "right": 106, "delete": 111, "home": 102, "end": 107,
         "pageup": 104, "pagedown": 109, "grave": 41, "tilde": 41}
NAMES.update({chr(0x61 + i): VK[0x41 + i] for i in range(26)})
NAMES.update({str(i): VK[0x30 + i] for i in range(10)})
NAMES.update({f"f{i + 1}": VK[0x70 + i] for i in range(12)})
# US layout for `type`
CHARS = {" ": (57, False), "\n": (28, False), "-": (12, False), "=": (13, False), "[": (26, False), "]": (27, False),
         ";": (39, False), "'": (40, False), "`": (41, False), "\\": (43, False), ",": (51, False), ".": (52, False),
         "/": (53, False), "_": (12, True), "+": (13, True), "{": (26, True), "}": (27, True), ":": (39, True),
         '"': (40, True), "~": (41, True), "|": (43, True), "<": (51, True), ">": (52, True), "?": (53, True),
         "!": (2, True), "@": (3, True), "#": (4, True), "$": (5, True), "%": (6, True), "^": (7, True),
         "&": (8, True), "*": (9, True), "(": (10, True), ")": (11, True)}


def keycode(k: str) -> int:
    k = k.strip().lower()
    if k in NAMES:
        return NAMES[k]
    try:
        vk = int(k, 16) if k.startswith("0x") else int(k)
    except ValueError:
        raise RuntimeError(f"unknown key {k!r} (Windows VK like 0x1B, or a name: esc, a, f5, space...)")
    if vk not in VK:
        raise RuntimeError(f"no evdev mapping for VK {k}")
    return VK[vk]


class UInput:
    """A virtual keyboard + mouse on /dev/uinput (legacy uinput_user_dev setup, stdlib only)."""

    def __init__(self, name=b"universal-modder"):
        try:
            self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        except PermissionError:
            die("no write access to /dev/uinput: see `um win setup`")
        for ev in (EV_KEY, EV_REL):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        for code in list(range(1, 128)) + [BTN_LEFT, BTN_RIGHT, 0x112]:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        for rel in (REL_X, REL_Y, REL_WHEEL):
            fcntl.ioctl(self.fd, UI_SET_RELBIT, rel)
        dev = struct.pack("80sHHHHi", name, 0x03, 0x1209, 0x5555, 1, 0) + b"\0" * (4 * 64 * 4)
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        time.sleep(0.3)  # let the compositor pick up the new device

    def emit(self, typ, code, value, sync=True):
        os.write(self.fd, struct.pack("llHHi", 0, 0, typ, code, value))
        if sync:
            os.write(self.fd, struct.pack("llHHi", 0, 0, EV_SYN, 0, 0))

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


class Drive:
    """WinDrive's line protocol on Hyprland: d = Drive("Palworld"); d.focus(); d.click(640, 360); d.key("0x1B")."""

    def __init__(self, proc: str):
        self.win = find_window(exe=proc)
        self.addr = self.win["address"]
        self.ui = UInput()
        self.ready = f"ready {self.win['exe']} pid={self.win['pid']} {self.addr}"

    def _win(self) -> dict:
        for c in hyprctl("clients"):
            if c["address"] == self.addr:
                return c
        raise RuntimeError("error: window is gone")

    def _foreground(self):
        if hyprctl("activewindow").get("address") != self.addr:
            raise RuntimeError("error: game is not the foreground window")

    def _to(self, x, y):
        c = self._win()
        move_cursor(c["at"][0] + int(float(x)), c["at"][1] + int(float(y)))
        time.sleep(0.02)

    def _key(self, code, mode="tap"):
        if mode in ("tap", "down"):
            self.ui.emit(EV_KEY, code, 1)
        if mode == "tap":
            time.sleep(0.03)
        if mode in ("tap", "up"):
            self.ui.emit(EV_KEY, code, 0)

    def _button(self, right, down):
        self.ui.emit(EV_KEY, BTN_RIGHT if right else BTN_LEFT, 1 if down else 0)

    def run(self, line: str) -> str:
        n = line.split()
        if not n:
            return "error: empty command"
        cmd, a = n[0], n[1:]
        if cmd == "focus":
            focus_window(self.addr)
            time.sleep(0.2)
            return "ok" if hyprctl("activewindow").get("address") == self.addr else "fail"
        if cmd == "rect":
            c = self._win()
            return f"{c['at'][0]} {c['at'][1]} {c['size'][0]} {c['size'][1]}"
        if cmd == "title":
            return self._win()["title"]
        if cmd == "fg":
            w = hyprctl("activewindow")
            return exe_name(w["pid"]) if w.get("pid") else "none"
        if cmd == "idle":
            return "unknown"  # Wayland doesn't expose other clients' input times: ask the user
        if cmd in ("scanmode", "untop"):
            return "ok"  # uinput already sends hardware keycodes; no topmost flag on Hyprland
        if cmd == "size":
            resize_window(self.addr, int(a[0]), int(a[1]))
            return "ok"
        self._foreground()
        if cmd == "move":
            self._to(a[0], a[1])
        elif cmd == "click":
            self._to(a[0], a[1])
            right = len(a) > 2 and a[2] == "right"
            self._button(right, True)
            time.sleep(0.04)
            self._button(right, False)
        elif cmd == "mdown":
            self._to(a[0], a[1])
            self._button(len(a) > 2 and a[2] == "right", True)
        elif cmd == "mup":
            self._button(bool(a) and a[0] == "right", False)
        elif cmd == "drag":
            self._to(a[0], a[1])
            self._button(False, True)
            for i in range(1, 11):
                time.sleep(0.02)
                self._to(int(a[0]) + (int(a[2]) - int(a[0])) * i / 10, int(a[1]) + (int(a[3]) - int(a[1])) * i / 10)
            self._button(False, False)
        elif cmd == "rel":
            self.ui.emit(EV_REL, REL_X, int(a[0]), sync=False)
            self.ui.emit(EV_REL, REL_Y, int(a[1]))
        elif cmd == "key":
            self._key(keycode(a[0]), a[1] if len(a) > 1 else "tap")
        elif cmd == "hold":
            code = keycode(a[0])
            self._key(code, "down")
            time.sleep(int(a[1]) / 1000)
            self._key(code, "up")
        elif cmd == "type":
            for ch in line.split(" ", 1)[1] if len(n) > 1 else "":
                code, shift = CHARS.get(ch) or (NAMES.get(ch.lower()), ch.isupper())
                if code is None:
                    raise RuntimeError(f"error: can't type {ch!r} (US layout only)")
                if shift:
                    self._key(SHIFT, "down")
                self._key(code)
                if shift:
                    self._key(SHIFT, "up")
                time.sleep(0.01)
        elif cmd == "wheel":
            self.ui.emit(EV_REL, REL_WHEEL, max(1, abs(int(a[0])) // 120) * (1 if int(a[0]) > 0 else -1))
        else:
            return f"error: unknown command {cmd}"
        return "ok"

    def cmd(self, line: str, retry: bool = True) -> str:
        try:
            return self.run(line)
        except RuntimeError as e:
            msg = str(e) if str(e).startswith("error") else f"error: {e}"
            if "foreground" in msg and retry:
                self.run("focus")
                time.sleep(0.3)
                return self.cmd(line, retry=False)
            raise RuntimeError(f"{line}: {msg}")

    def focus(self):
        return self.cmd("focus") == "ok"

    def rect(self):
        return tuple(int(v) for v in self.cmd("rect").split())

    def click(self, x, y, right=False, pause=0.3):
        self.cmd(f"click {int(x)} {int(y)}" + (" right" if right else ""))
        time.sleep(pause)

    def key(self, vk, mode="tap", pause=0.12):
        self.cmd(f"key {vk} {mode}")
        time.sleep(pause)

    def hold(self, vk, ms):
        self.cmd(f"hold {vk} {int(ms)}")

    def type(self, text):
        self.cmd("type " + text)

    def drag(self, x0, y0, x1, y1):
        self.cmd(f"drag {int(x0)} {int(y0)} {int(x1)} {int(y1)}")

    def wheel(self, d):
        self.cmd(f"wheel {int(d)}")

    def close(self):
        self.ui.close()


# --------------------------------------------------------------------------- registry (Proton prefix)


def proton_wine(appid: str) -> tuple[Path, Path]:
    from um.scan import proton_prefix
    pfx = proton_prefix(str(appid))
    if not pfx:
        die(f"no Proton prefix for appid {appid} (run the game once through Proton)")
    info = (pfx.parent / "config_info")
    for line in info.read_text(errors="replace").splitlines() if info.exists() else []:
        # config_info lists files under the Proton build that created the prefix
        m = re.match(r"(.*/files)/", line)
        if m and (Path(m.group(1)) / "bin/wine").exists():
            return pfx, Path(m.group(1)) / "bin/wine"
    die(f"can't find the Proton build for {pfx} (see {info})")


def reg(action: str, key: str, value=None, data=None, typ="REG_DWORD", appid=None):
    if not appid:
        die("on Linux the registry lives in the game's Proton prefix: pass --appid <steam appid>")
    pfx, wine = proton_wine(appid)
    env = dict(os.environ, WINEPREFIX=str(pfx), WINEDEBUG="-all")
    if action == "get":
        cmd = [str(wine), "reg", "query", key] + (["/v", value] if value else [])
    else:
        from um.common import data_dir
        backup = data_dir() / "reg-backups"
        backup.mkdir(exist_ok=True)
        bfile = backup / f"{appid}-{re.sub(r'[^A-Za-z0-9]+', '_', key)}-{time.strftime('%Y%m%d-%H%M%S')}.reg"
        subprocess.run([str(wine), "reg", "export", key, "Z:" + str(bfile).replace("/", "\\"), "/y"], env=env, capture_output=True)
        print("backup:", bfile)
        cmd = [str(wine), "reg", "add", key, "/v", value, "/t", typ, "/d", data, "/f"]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    print((r.stdout or r.stderr).replace("\r", "").strip())
