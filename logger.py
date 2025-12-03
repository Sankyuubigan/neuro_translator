import sys
from PySide6.QtCore import QObject, Signal

# Глобальный объект для сигналов логгера
class LoggerSignals(QObject):
    log_signal = Signal(str)

global_signals = LoggerSignals()

class StreamRedirector:
    """Перехватывает stdout/stderr и отправляет в GUI"""
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, text):
        # 1. В консоль
        if self.original_stream:
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except: pass
        
        # 2. В GUI
        try:
            if text:
                global_signals.log_signal.emit(str(text))
        except: pass

    def flush(self):
        if self.original_stream:
            try: self.original_stream.flush()
            except: pass

def setup_logger():
    if not isinstance(sys.stdout, StreamRedirector):
        sys.stdout = StreamRedirector(sys.__stdout__)
        sys.stderr = StreamRedirector(sys.__stderr__)