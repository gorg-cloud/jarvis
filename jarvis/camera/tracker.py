"""
jarvis/camera/tracker.py
MediaPipe hand tracking wrapper (Tasks API). Turns a webcam RGB frame into
a list of 21 normalized (x, y) hand landmarks per detected hand.
"""
from __future__ import annotations

import os

import mediapipe as mp
import numpy as np

from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

_MODEL = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")


class HandTracker:
    """Thin wrapper around MediaPipe's HandLandmarker (Tasks API)."""

    def __init__(self, model_path: str | None = None, num_hands: int = 1):
        path = model_path or _MODEL
        base_options = mp_python.BaseOptions(model_asset_path=path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=num_hands,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_rgb: np.ndarray) -> list:
        """frame_rgb: contiguous HxWx3 uint8 numpy array (RGB).

        Returns a list of hands; each hand is a list of 21 (x, y) tuples
        normalized to 0..1 (x grows right, y grows down in the RAW frame).
        """
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._landmarker.detect(img)
        hands = []
        for hand in result.hand_landmarks:
            hands.append([(lm.x, lm.y) for lm in hand])
        return hands

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass
