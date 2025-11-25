import sys
import os
import json
import time
import re
import traceback

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                               QWidget, QTextEdit, QPushButton, QLabel, QMessageBox, 
                               QProgressBar, QComboBox, QCheckBox, QGroupBox, QTabWidget, 
                               QLineEdit, QFileDialog)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject, QMetaObject

# =================================================================================
# ГЛОБАЛЬНАЯ СИСТЕМА ЛОГОВ (БЕЗ ОЧЕРЕДЕЙ, НАПРЯМУЮ)
# =================================================================================

class LoggerSignals(QObject):
    # Сигнал, который передает текст (str)
    log_signal = Signal(str)

# Создаем глобальный экземпляр сигналов ДО всего остального
global_signals = LoggerSignals()

class StreamRedirector:
    """Класс, который заменяет sys.stdout и sys.stderr"""
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, text):
        # 1. Пишем в черную консоль (чтобы ты видел, что процесс идет)
        if self.original_stream:
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except: pass
        
        # 2. Отправляем в GUI через сигнал
        # Эмит сигнала потокобезопасен в Qt, он сам встанет в очередь событий
        try:
            if text:
                global_signals.log_signal.emit(str(text))
        except:
            pass # Если приложение закрывается, может быть ошибка, игнорим

    def flush(self):
        if self.original_stream:
            try: self.original_stream.flush()
            except: pass

# Сохраняем оригиналы
ORIGINAL_STDOUT = sys.__stdout__
ORIGINAL_STDERR = sys.__stderr__

# ПОДМЕНЯЕМ ПОТОКИ ПРЯМО СЕЙЧАС
# Теперь любой print() в программе вызовет global_signals.log_signal.emit()
sys.stdout = StreamRedirector(ORIGINAL_STDOUT)
sys.stderr = StreamRedirector(ORIGINAL_STDERR)

print("--- СТАРТ СИСТЕМЫ ЛОГОВ ---")

# =================================================================================

try:
    import ctranslate2
    import sentencepiece as spm
    from huggingface_hub import snapshot_download
    print("Библиотеки загружены.")
except ImportError as e:
    print(f"CRITICAL ERROR: {e}")
    sys.exit(1)

CONFIG_FILE = "settings.json"
DEFAULT_MODEL_REPO = "santhosh/madlad400-3b-ct2"
LANGUAGES = {
    "Русский": "ru", "English": "en", "German": "de", "French": "fr",
    "Spanish": "es", "Ukrainian": "uk", "Italian": "it", "Chinese": "zh"
}

# === ДВИЖОК ===
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
            # intra_threads=4 для стабильности
            self.translator = ctranslate2.Translator(model_path, device="cpu", intra_threads=4)
            print("CTranslate2 готов.")
            return True, "Готово"
        except Exception as e:
            print(f"Ошибка движка: {e}")
            return False, str(e)

    def translate(self, text, target_lang_code, beam_size=1):
        if not self.translator: return "Ошибка: движок не готов"
        try:
            input_text = f"<2{target_lang_code}> {text}"
            source_tokens = self.sp.encode_as_pieces(input_text)
            results = self.translator.translate_batch(
                [source_tokens], beam_size=beam_size, max_decoding_length=300
            )
            return self.sp.decode(results[0].hypotheses[0])
        except Exception as e:
            print(f"Ошибка перевода: {e}")
            return f"Error: {e}"

engine = TranslatorEngine()

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
        print(f"Start Translation -> {self.code}")
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

# === GUI ===
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Translator Pro (Direct Signals)")
        self.resize(850, 650)
        self.apply_styles()
        
        self.config = ConfigManager.load()
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.tab_translate = QWidget()
        self.tab_settings = QWidget()
        self.tab_logs = QWidget()
        
        self.setup_translate_ui()
        self.setup_settings_ui()
        self.setup_logs_ui()
        
        self.tabs.addTab(self.tab_translate, "Перевод")
        self.tabs.addTab(self.tab_settings, "Настройки")
        self.tabs.addTab(self.tab_logs, "Логи")

        # === ПОДКЛЮЧЕНИЕ СИГНАЛА К СЛОТУ ===
        # Как только print() сработает где угодно, вызовется self.append_log
        global_signals.log_signal.connect(self.append_log)
        
        print("GUI инициализирован. Связь установлена.")
        
        # Загрузка
        self.check_and_load_model()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #ffffff; font-family: 'Segoe UI', sans-serif; }
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { 
                background: #3e3e3e; 
                color: #b0b0b0; 
                padding: 10px 20px; 
            }
            QTabBar::tab:selected { 
                background: #505050; 
                color: #ffffff; 
                border-bottom: 3px solid #007ACC; 
                font-weight: bold;
            }
            QTextEdit, QLineEdit { background: #3b3b3b; border: 1px solid #555; padding: 5px; color: #fff; }
            QPushButton { background: #007ACC; padding: 8px; border-radius: 4px; font-weight: bold; border: none;}
            QPushButton:hover { background: #005A9E; }
            QPushButton:disabled { background: #444; color: #888; }
            QComboBox { background: #3b3b3b; padding: 5px; color: white; border: 1px solid #555;}
            QGroupBox { border: 1px solid #555; margin-top: 15px; padding-top: 15px; font-weight: bold; color: #ddd;}
            QProgressBar { border: 1px solid #555; text-align: center; }
            QProgressBar::chunk { background-color: #007ACC; }
        """)

    def setup_translate_ui(self):
        l = QVBoxLayout(self.tab_translate)
        top = QHBoxLayout()
        self.lang = QComboBox()
        self.lang.addItems(LANGUAGES.keys())
        top.addWidget(QLabel("Цель:"))
        top.addWidget(self.lang)
        self.auto = QCheckBox("Авто (RU/EN)")
        self.auto.setChecked(True)
        top.addWidget(self.auto)
        top.addStretch()
        self.speed = QComboBox()
        self.speed.addItems(["Турбо (Beam 1)", "Баланс (Beam 2)", "Качество (Beam 4)"])
        top.addWidget(QLabel("Режим:"))
        top.addWidget(self.speed)
        l.addLayout(top)
        
        self.inp = QTextEdit()
        self.inp.setPlaceholderText("Введите текст...")
        self.inp.textChanged.connect(self.on_text_change)
        l.addWidget(self.inp)
        
        self.btn = QPushButton("ПЕРЕВЕСТИ")
        self.btn.clicked.connect(self.start_tr)
        self.btn.setFixedHeight(50)
        self.btn.setStyleSheet("background-color: #2E7D32;")
        l.addWidget(self.btn)
        
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setStyleSheet("background-color: #222;")
        l.addWidget(self.out)
        self.stat = QLabel("...")
        l.addWidget(self.stat)

    def setup_settings_ui(self):
        l = QVBoxLayout(self.tab_settings)
        gb = QGroupBox("Папка модели")
        gl = QVBoxLayout()
        hl = QHBoxLayout()
        self.path_ed = QLineEdit(self.config.get("model_path", ""))
        self.br_btn = QPushButton("...")
        self.br_btn.setFixedWidth(40)
        self.br_btn.clicked.connect(self.browse)
        hl.addWidget(self.path_ed)
        hl.addWidget(self.br_btn)
        gl.addLayout(hl)
        self.lbl_st = QLabel("Статус: ?")
        gl.addWidget(self.lbl_st)
        self.load_btn = QPushButton("Загрузить")
        self.load_btn.clicked.connect(self.check_and_load_model)
        gl.addWidget(self.load_btn)
        gb.setLayout(gl)
        l.addWidget(gb)
        
        gb2 = QGroupBox("Интернет")
        gl2 = QVBoxLayout()
        gl2.addWidget(QLabel(f"Repo: {DEFAULT_MODEL_REPO}"))
        self.dl_btn = QPushButton("СКАЧАТЬ МОДЕЛЬ")
        self.dl_btn.setStyleSheet("background-color: #D32F2F;")
        self.dl_btn.clicked.connect(self.dl_start)
        gl2.addWidget(self.dl_btn)
        self.prog = QProgressBar()
        self.prog.hide()
        gl2.addWidget(self.prog)
        gb2.setLayout(gl2)
        l.addWidget(gb2)
        l.addStretch()

    def setup_logs_ui(self):
        l = QVBoxLayout(self.tab_logs)
        # ВАЖНО: Используем append для добавления текста, поэтому setReadOnly=True
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        # Ярко-зеленый на черном
        self.logs.setStyleSheet("background-color: #000000; color: #00FF00; font-family: Consolas, monospace; font-size: 13px; border: 1px solid #555;")
        l.addWidget(self.logs)
        
        h = QHBoxLayout()
        clr = QPushButton("Очистить")
        clr.clicked.connect(self.logs.clear)
        h.addWidget(clr)
        tst = QPushButton("ТЕСТ ЛОГА (ЖМИ)")
        tst.clicked.connect(lambda: print("Тестовый лог работает!"))
        h.addWidget(tst)
        l.addLayout(h)

    # === ГЛАВНЫЙ СЛОТ ДЛЯ ЛОГОВ ===
    @Slot(str)
    def append_log(self, text):
        # Если пришла пустая строка - игнорим
        if not text: return
        try:
            # Убираем лишние переносы, чтобы не было пустых строк
            text = text.rstrip()
            if text:
                self.logs.append(text) 
                # Прокрутка вниз
                self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())
        except: pass

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Выбор папки", self.path_ed.text())
        if d: self.path_ed.setText(d)

    def check_and_load_model(self):
        p = self.path_ed.text().strip()
        if not p: return
        self.config["model_path"] = p
        ConfigManager.save(self.config)
        self.btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self.stat.setText("Загрузка...")
        self.loader = LoaderThread(p)
        self.loader.finished_signal.connect(self.on_load_done)
        self.loader.daemon = True
        self.loader.start()

    @Slot(bool, str)
    def on_load_done(self, s, m):
        self.load_btn.setEnabled(True)
        self.lbl_st.setText(m)
        self.lbl_st.setStyleSheet(f"color: {'#0F0' if s else '#F00'}; font-weight: bold;")
        print(f"Результат загрузки: {m}")
        if s:
            self.btn.setEnabled(True)
            self.stat.setText("Готов")
        else:
            self.btn.setText("Ошибка")
            QMessageBox.warning(self, "Ошибка", m)

    def dl_start(self):
        p = self.path_ed.text().strip()
        if not p or not os.path.exists(p): 
            QMessageBox.warning(self, "Путь", "Папка не существует")
            return
        self.dl_btn.setEnabled(False)
        self.prog.setRange(0,0)
        self.prog.show()
        self.tabs.setCurrentWidget(self.tab_logs)
        self.dl = DownloaderThread(p)
        self.dl.finished_signal.connect(self.on_dl_done)
        self.dl.daemon = True
        self.dl.start()

    @Slot(bool, str)
    def on_dl_done(self, s, m):
        self.prog.hide()
        self.dl_btn.setEnabled(True)
        if s: 
            QMessageBox.information(self, "OK", "Скачано!")
            self.check_and_load_model()
        else: 
            QMessageBox.critical(self, "Err", m)

    def on_text_change(self):
        if not self.auto.isChecked(): return
        t = self.inp.toPlainText()
        if not t: return
        has_ru = bool(re.search('[а-яА-Я]', t))
        curr = self.lang.currentText()
        if has_ru and curr != "English": self.lang.setCurrentText("English")
        elif not has_ru and curr != "Русский" and curr == "English": self.lang.setCurrentText("Русский")

    def start_tr(self):
        t = self.inp.toPlainText().strip()
        if not t: return
        bm = [1, 2, 4][self.speed.currentIndex()]
        tg = LANGUAGES[self.lang.currentText()]
        self.btn.setEnabled(False)
        self.stat.setText("Думаю...")
        self.worker = TranslateThread(t, tg, bm)
        self.worker.result_signal.connect(self.on_tr_done)
        self.worker.daemon = True
        self.worker.start()

    @Slot(str, float)
    def on_tr_done(self, txt, tm):
        self.out.setPlainText(txt)
        self.btn.setEnabled(True)
        self.stat.setText(f"{tm:.2f} сек")
        print(f"Готово: {tm:.2f}s")

    def closeEvent(self, e):
        os._exit(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())