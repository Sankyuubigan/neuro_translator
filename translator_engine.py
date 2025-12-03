import os
import json
import time
import traceback
import sentencepiece as spm
from PySide6.QtCore import QThread, Signal

# Попытка импорта движка
try:
    import ctranslate2
    from huggingface_hub import snapshot_download
except ImportError:
    print("CRITICAL: ctranslate2 not found")

CONFIG_FILE = "settings.json"
DEFAULT_MODEL_REPO = "santhosh/madlad400-3b-ct2"
LANGUAGES = {
    "Русский": "ru", "English": "en", "German": "de", "French": "fr",
    "Spanish": "es", "Ukrainian": "uk", "Italian": "it", "Chinese": "zh"
}

class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
            except: pass
        return {"model_path": os.getcwd()}
    @staticmethod
    def save(data):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

class TranslatorEngine:
    def __init__(self):
        self.translator = None
        self.sp = None

    def load(self, model_path):
        print(f"Загрузка движка из: {model_path}")
        sp_path = os.path.join(model_path, "sentencepiece.model")
        model_bin = os.path.join(model_path, "model.bin")
        
        if not os.path.exists(sp_path) or not os.path.exists(model_bin):
            return False, "Файлы не найдены!"

        try:
            self.sp = spm.SentencePieceProcessor()
            self.sp.load(sp_path)
            self.translator = ctranslate2.Translator(model_path, device="cpu", intra_threads=4)
            print("CTranslate2 готов.")
            return True, "Готово"
        except Exception as e:
            print(f"Ошибка движка: {e}")
            return False, str(e)

    def translate(self, text, target_lang_code, beam_size=1):
        if not self.translator: return "Ошибка: движок не готов"
        try:
            # Разбиваем на строки, чтобы сохранить форматирование
            lines = text.split('\n')
            results = []
            for line in lines:
                if not line.strip():
                    results.append("")
                    continue
                
                input_text = f"<2{target_lang_code}> {line}"
                source_tokens = self.sp.encode_as_pieces(input_text)
                res = self.translator.translate_batch(
                    [source_tokens], beam_size=beam_size, max_decoding_length=300
                )
                results.append(self.sp.decode(res[0].hypotheses[0]))
            
            return "\n".join(results)
        except Exception as e:
            print(f"Ошибка перевода: {e}")
            return f"Error: {e}"

# Глобальный экземпляр движка
engine = TranslatorEngine()

# === ПОТОКИ ===
class LoaderThread(QThread):
    finished_signal = Signal(bool, str)
    def __init__(self, path):
        super().__init__()
        self.path = path
    def run(self):
        try:
            s, m = engine.load(self.path)
            self.finished_signal.emit(s, m)
        except Exception as e:
            print(traceback.format_exc())
            self.finished_signal.emit(False, str(e))

class TranslateThread(QThread):
    result_signal = Signal(str, float)
    def __init__(self, text, code, beam):
        super().__init__()
        self.text, self.code, self.beam = text, code, beam
    def run(self):
        t = time.time()
        print(f"Translate -> {self.code}")
        try:
            res = engine.translate(self.text, self.code, self.beam)
            self.result_signal.emit(res, time.time() - t)
        except:
            print(traceback.format_exc())
            self.result_signal.emit("Error", 0)

class DownloaderThread(QThread):
    finished_signal = Signal(bool, str)
    def __init__(self, target_folder):
        super().__init__()
        self.target_folder = target_folder
    def run(self):
        print("Начинаем скачивание...")
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        try:
            snapshot_download(repo_id=DEFAULT_MODEL_REPO, local_dir=self.target_folder, local_dir_use_symlinks=False, resume_download=True, tqdm_class=None)
            print("Скачивание завершено.")
            self.finished_signal.emit(True, "OK")
        except Exception as e:
            print(f"Ошибка скачивания: {e}")
            self.finished_signal.emit(False, str(e))