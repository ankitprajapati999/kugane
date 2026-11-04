# core/stt/stt_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
from core.stt.stt_module import KuganeSTTEngine

class STTWorkerThread(QThread):
    transcription_ready = pyqtSignal(str)
    status_updated = pyqtSignal(str)

    def __init__(self, model="base", device="auto"):
        super().__init__()
        self.model = model
        self.device = device
        self.engine = None

    def run(self):
        def handle_new_transcript(text):
            self.transcription_ready.emit(text)

        try:
            # 1. Update UI to show loading state & progress bar
            self.status_updated.emit("Loading model...")
            
            self.engine = KuganeSTTEngine(
                model_size=self.model,
                device=self.device,
                on_transcript=handle_new_transcript
            )
            
            # 2. Pre-load model weights into GPU VRAM
            self.status_updated.emit("Allocating GPU weights...")
            self.engine._load_model()
            
            # 3. Transition to Listening state and open the microphone stream via engine.start()
            self.status_updated.emit("Listening...")
            self.engine.start()
            
        except Exception as e:
            self.status_updated.emit(f"Error: {e}")

    def stop(self):
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
        self.quit()
        self.wait()