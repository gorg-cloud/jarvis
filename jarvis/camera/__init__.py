"""
jarvis/camera
JARVIS Gesture Control — use the webcam to drive your Mac like Tony Stark:

  Mode 1 (CURSOR): move your index finger to move the mouse; pinch your
  thumb and index finger together to click (precise — normalized by hand
  size with a short hold). Peace sign (✌️) held 3s closes the frontmost
  app; a fist swipe left/right switches desktops.

  Mode 2 (WHITEBOARD): pinch to write — draw with your finger, pick marker
  color (keys 1-6) and size, and JARVIS auto-converts handwriting to text.

  Mode 3 (PROJECT): a clean black & white fullscreen canvas with a small
  JARVIS panel — chat (text + voice), pin screenshots / camera frames /
  pasted images, add & remove notes, suggestions, and save to Obsidian.

Run with:  python -m jarvis.camera   (or the packaged app: JARVIS.app --gestures)
Or from the chat/voice:  "open gesture control"  (gestures.start)
Or:  "start a new project"  (project.start → opens straight into Mode 3)
"""
