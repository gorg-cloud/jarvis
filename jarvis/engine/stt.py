"""
jarvis/engine/stt.py
Speech-to-text abstraction. Switches between Google (default) and local Whisper.
Config: env STT_ENGINE = 'google' | 'whisper'.
"""
import os
import tempfile
import speech_recognition as sr

STT_ENGINE = os.getenv("STT_ENGINE", "google").lower()


class STT:
    """Base interface: recognize(audio) -> str"""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 400
        self.recognizer.dynamic_energy_threshold = True

    def listen(self, source, phrase_time_limit: int = 30, timeout=None):
        """Capture audio from a Microphone source."""
        return self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

    def recognize(self, audio) -> str:
        raise NotImplementedError


class GoogleSTT(STT):
    """Default Google web speech. Requires internet."""

    def recognize(self, audio) -> str:
        return self.recognizer.recognize_google(audio)


class WhisperSTT(STT):
    """
    Local Whisper transcription. More private, works offline, better with accents.
    Requires: pip install faster-whisper
    Config: WHISPER_MODEL = 'tiny' | 'base' | 'small' | 'medium' (default 'base')
    """
    def __init__(self):
        super().__init__()
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError(
                "Whisper STT needs faster-whisper. Run: pip install faster-whisper"
            ) from e
        model_name = os.getenv("WHISPER_MODEL", "base")
        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def recognize(self, audio) -> str:
        # Save audio to temp wav, transcribe
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        with open(path, "wb") as f:
            f.write(audio.get_wav_data())
        segments, _ = self._model.transcribe(path, beam_size=1)
        text = " ".join(s.text for s in segments).strip()
        try:
            os.unlink(path)
        except Exception:
            pass
        if not text:
            raise sr.UnknownValueError()
        return text


def make_stt() -> STT:
    """Factory. Falls back to Google if Whisper unavailable."""
    if STT_ENGINE == "whisper":
        try:
            return WhisperSTT()
        except Exception as e:
            print(f"⚠️ Whisper STT init failed ({e}); falling back to Google.")
    return GoogleSTT()
