# main.py
import sys
from PyQt6.QtWidgets import QApplication
from ui.island_window import DynamicIslandWindow
from core.stt.stt_worker import STTWorkerThread

def handle_query_dispatch(prompt: str):
    print(f"[Kugane Pipeline] Dispatching prompt: '{prompt}'")

def main():
    app = QApplication(sys.argv)
    
    # 1. Initialize UI (Starts in amber 'Loading...' state)
    window = DynamicIslandWindow(on_user_submit_callback=handle_query_dispatch)
    window.show()
    
    # 2. Initialize STT Background Worker Thread
    stt_worker = STTWorkerThread(model="base", device="auto")
    
    # 3. Wire signals
    stt_worker.transcription_ready.connect(window.display_transcription)
    stt_worker.status_updated.connect(window.update_status)  # Updates dot & status label
    
    # 4. Start background thread
    stt_worker.start()
    
    exit_code = app.exec()
    stt_worker.stop()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()