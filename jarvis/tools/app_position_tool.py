"""
jarvis/tools/app_position_tool.py
Open/resize/move an application window to a specific region on screen.
Used by HUD to embed apps in defined areas (e.g. open YouTube in bottom-right quadrant).

Positions: "left", "right", "center", "top-left", "top-right", "bottom-left", "bottom-right",
           "top-half", "bottom-half", "left-half", "right-half", "full"
Or exact: {"x": int, "y": int, "width": int, "height": int} via x/y/w/h args.
"""
import subprocess

from jarvis.platform import launch_app, macos_only


def open_app_positioned(
    app_name: str,
    position: str = "right",
    screen: str = "",
    x: int = 0,
    y: int = 0,
    width: int = 800,
    height: int = 600,
) -> dict:
    """
    Open an app and position its window.

    Parameters
    ----------
    app_name : str
        Application name (e.g. "Safari", "YouTube").
    position : str
        Preset position: left, right, center, top-left, top-right, bottom-left,
        bottom-right, top-half, bottom-half, left-half, right-half, full.
        Ignored if x/y/width/height are explicitly provided.
    screen : str
        Target screen name. Empty = main screen. "external" = first non-primary.
    x, y, width, height : int
        Explicit pixel coordinates. If all non-zero, overrides position.
    """
    blocked = macos_only("Window positioning")
    if blocked:
        return {"app": app_name, "status": "failed", "error": blocked}
    # Open app first
    try:
        launch_app(app_name)
    except Exception as e:
        return {"app": app_name, "status": "failed", "error": f"open failed: {e}"}

    import time
    time.sleep(1.5)  # wait for window to appear

    # Build position/size script
    script = f'''
    set appName to "{app_name}"
    '''

    if x or y or width or height:
        # Explicit coordinates
        script += f'''
    tell application "System Events"
        tell process appName
            set frontmost to true
            delay 0.3
            try
                set posX to {x}
                set posY to {y}
                set szW to {width}
                set szH to {height}
                set position of front window to {{posX, posY}}
                set size of front window to {{szW, szH}}
                return "OK"
            on error e
                return "FAIL:" & e
            end try
        end tell
    end tell
    '''
    else:
        # Preset position — compute from screen bounds
        screen_filter = ""
        if screen == "external":
            screen_filter = 'whose role is not "AXStandardWindow"'

        script += f'''
    tell application "System Events"
        tell process appName
            set frontmost to true
            delay 0.3
            try
                set win to front window
                set {{sw, sh}} to size of win
                set {{sx, sy}} to position of win
                -- get screen bounds (approximate: use main screen)
                try
                    set screenBounds to (do shell script "system_profiler SPDisplaysDataType | grep Resolution")
                end try
                -- Use macOS 12+ geometry
                try
                    tell application "System Events"
                        set mainScreen to first area of first screen
                        set sw2 to item 3 of mainScreen
                        set sh2 to item 4 of mainScreen
                    end tell
                    set sw to sw2
                    set sh to sh2
                end try
                set p to "{position}"
                set m to 50 -- margin
                if p is "left" then
                    set position of win to {{m, m}}
                    set size of win to {{sw / 2 - m * 1.5, sh - m * 2}}
                else if p is "right" then
                    set position of win to {{sw / 2 + m / 2, m}}
                    set size of win to {{sw / 2 - m * 1.5, sh - m * 2}}
                else if p is "center" then
                    set position of win to {{m, m}}
                    set size of win to {{sw - m * 2, sh - m * 2}}
                else if p is "top-left" then
                    set position of win to {{m, m}}
                    set size of win to {{sw / 2 - m * 1.5, sh / 2 - m * 1.5}}
                else if p is "top-right" then
                    set position of win to {{sw / 2 + m / 2, m}}
                    set size of win to {{sw / 2 - m * 1.5, sh / 2 - m * 1.5}}
                else if p is "bottom-left" then
                    set position of win to {{m, sh / 2 + m / 2}}
                    set size of win to {{sw / 2 - m * 1.5, sh / 2 - m * 1.5}}
                else if p is "bottom-right" then
                    set position of win to {{sw / 2 + m / 2, sh / 2 + m / 2}}
                    set size of win to {{sw / 2 - m * 1.5, sh / 2 - m * 1.5}}
                else if p is "top-half" then
                    set position of win to {{m, m}}
                    set size of win to {{sw - m * 2, sh / 2 - m * 1.5}}
                else if p is "bottom-half" then
                    set position of win to {{m, sh / 2 + m / 2}}
                    set size of win to {{sw - m * 2, sh / 2 - m * 1.5}}
                else if p is "left-half" then
                    set position of win to {{m, m}}
                    set size of win to {{sw / 2 - m * 1.5, sh - m * 2}}
                else if p is "right-half" then
                    set position of win to {{sw / 2 + m / 2, m}}
                    set size of win to {{sw / 2 - m * 1.5, sh - m * 2}}
                else if p is "full" then
                    set position of win to {{0, 0}}
                    set size of win to {{sw, sh}}
                end if
                return "OK"
            on error e
                return "FAIL:" & e
            end try
        end tell
    end tell
    '''

    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if "OK" in r.stdout:
            return {"app": app_name, "position": position, "status": "positioned"}
        return {"app": app_name, "position": position, "status": "failed", "error": r.stdout.strip() or r.stderr.strip()}
    except Exception as e:
        return {"app": app_name, "status": "failed", "error": str(e)}
