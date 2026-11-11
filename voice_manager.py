import queue
import threading
import time

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False


class VoiceManager:
    def __init__(self, config):
        self.config = config
        self.muted = False
        self.is_listening = False
        self._wake_active = False
        self._tts_queue: queue.Queue = queue.Queue()

        # Callbacks — set by the GUI after construction
        self.on_speech_result    = None   # fn(text: str | None, error: str | None)
        self.on_listening_change = None   # fn(is_listening: bool)
        self.on_wake_word        = None   # fn()

        # TTS worker (pyttsx3 must live in its own thread on macOS)
        if TTS_AVAILABLE and config.ENABLE_VOICE:
            threading.Thread(target=self._tts_worker, daemon=True).start()

        # STT / mic probe
        self.mic_available = False
        if STT_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self.recognizer.dynamic_energy_threshold = True
            try:
                with sr.Microphone():
                    pass
                self.mic_available = True
            except Exception:
                pass

    # ── TTS ───────────────────────────────────────────────────

    def _tts_worker(self):
        try:
            engine = pyttsx3.init()
            self._apply_voice(engine)
        except Exception:
            # TTS unavailable on this machine; drain queue silently
            while True:
                self._tts_queue.get()
                self._tts_queue.task_done()

        while True:
            text = self._tts_queue.get()
            if text is None:
                break
            if not self.muted:
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception:
                    # Engine crashed; reinit
                    try:
                        engine = pyttsx3.init()
                        self._apply_voice(engine)
                    except Exception:
                        pass
            self._tts_queue.task_done()

    def _apply_voice(self, engine):
        try:
            engine.setProperty("rate", self.config.VOICE_SPEED)
            voices = engine.getProperty("voices") or []
            gender = self.config.VOICE_GENDER
            for v in voices:
                name = (v.name or "").lower()
                if gender == "female" and any(x in name for x in ["female", "zira", "victoria", "samantha"]):
                    engine.setProperty("voice", v.id)
                    break
                if gender == "male" and any(x in name for x in ["male", "david", "daniel", "alex"]):
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            pass

    def speak(self, text: str):
        if TTS_AVAILABLE and self.config.ENABLE_VOICE and text:
            self._tts_queue.put(text)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted

    def update_voice_settings(self):
        """No-op — new settings take effect on the next TTS worker reinit cycle."""
        pass

    # ── STT ───────────────────────────────────────────────────

    def listen_once(self):
        """Start listening in background. Result delivered via on_speech_result callback."""
        if not self.mic_available or not STT_AVAILABLE:
            if self.on_speech_result:
                self.on_speech_result(None, "Microphone not available")
            return

        threading.Thread(target=self._listen_run, daemon=True).start()

    def _listen_run(self):
        self.is_listening = True
        if self.on_listening_change:
            self.on_listening_change(True)
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=12)
            text = self.recognizer.recognize_google(audio)
            if self.on_speech_result:
                self.on_speech_result(text, None)
        except sr.WaitTimeoutError:
            if self.on_speech_result:
                self.on_speech_result(None, "No speech detected")
        except sr.UnknownValueError:
            if self.on_speech_result:
                self.on_speech_result(None, "Could not understand audio")
        except Exception as exc:
            if self.on_speech_result:
                self.on_speech_result(None, str(exc))
        finally:
            self.is_listening = False
            if self.on_listening_change:
                self.on_listening_change(False)

    # ── Wake word ─────────────────────────────────────────────

    def start_wake_word_listener(self):
        if not self.mic_available or not STT_AVAILABLE:
            return
        if not self.config.ENABLE_WAKE_WORD:
            return
        self._wake_active = True
        threading.Thread(target=self._wake_loop, daemon=True).start()

    def _wake_loop(self):
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self.config.WAKE_WORD_ENERGY_THRESHOLD
        recognizer.dynamic_energy_threshold = False
        wake = self.config.WAKE_WORD.lower()

        while self._wake_active:
            if self.is_listening:
                time.sleep(0.5)
                continue
            try:
                with sr.Microphone() as source:
                    try:
                        audio = recognizer.listen(source, timeout=3, phrase_time_limit=3)
                        text = recognizer.recognize_google(audio).lower()
                        if wake in text and self.on_wake_word:
                            self.on_wake_word()
                    except (sr.WaitTimeoutError, sr.UnknownValueError):
                        pass
                    except Exception:
                        time.sleep(1)
            except Exception:
                time.sleep(2)

    def stop_wake_word_listener(self):
        self._wake_active = False
