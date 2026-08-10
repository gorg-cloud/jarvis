"""
jarvis/camera/selftest.py
Diagnostic: what can this process do right now, TCC-wise?

Checks (and logs to ~/.jarvis/debug.log):
  * AXIsProcessTrusted          — Accessibility granted?
  * CGPreflightPostEventAccess  — may we post synthetic events?
  * CGWarpMouseCursorPosition   — can we move the cursor WITHOUT accessibility?
  * CGEventPost (move)          — can we post a real mouse-move event?

Run:  JARVIS.app --gesture-selftest   (prints + logs)
"""
import os
import time


def run() -> int:
    lines: list[str] = []
    orig = None

    def dbg(msg: str) -> None:
        lines.append(msg)
        print(msg)

    try:
        import ApplicationServices
        dbg(f"AXIsProcessTrusted = {ApplicationServices.AXIsProcessTrusted()}")
    except Exception as exc:  # noqa: BLE001
        dbg(f"AX import failed: {exc}")

    try:
        import Quartz
        dbg(f"CGPreflightPostEventAccess = {Quartz.CGPreflightPostEventAccess()}")

        def _loc():
            ev = Quartz.CGEventCreate(None)
            return Quartz.CGEventGetLocation(ev)

        try:
            orig = _loc()
            target = (max(60.0, orig.x + 120.0), max(60.0, orig.y + 120.0))
            Quartz.CGWarpMouseCursorPosition(target)
            time.sleep(0.2)
            loc = _loc()
            ok = abs(loc.x - target[0]) < 60 and abs(loc.y - target[1]) < 60
            dbg(f"warp: target=({target[0]:.0f},{target[1]:.0f}) readback=({loc.x:.0f},{loc.y:.0f}) -> {'MOVED' if ok else 'NO MOVE'}")
        except Exception as exc:  # noqa: BLE001
            dbg(f"warp failed: {exc}")
        finally:
            if orig is not None:
                try:
                    Quartz.CGWarpMouseCursorPosition((orig.x, orig.y))
                except Exception:
                    pass

        try:
            target2 = (max(60.0, orig.x + 80.0), max(60.0, orig.y + 80.0))
            ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved,
                                               target2, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.2)
            loc = _loc()
            ok = abs(loc.x - target2[0]) < 60 and abs(loc.y - target2[1]) < 60
            dbg(f"post: target=({target2[0]:.0f},{target2[1]:.0f}) readback=({loc.x:.0f},{loc.y:.0f}) -> {'MOVED' if ok else 'NO MOVE'}")
        except Exception as exc:  # noqa: BLE001
            dbg(f"post failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        dbg(f"Quartz import failed: {exc}")

    try:
        with open(os.path.expanduser("~/.jarvis/debug.log"), "a", encoding="utf-8") as f:
            f.write(f"\n{time.strftime('%H:%M:%S')} [selftest]\n" + "\n".join(lines) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
