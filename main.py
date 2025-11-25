import sys
import os
import json
import time
import re
import ctranslate2
import sentencepiece as spm
from huggingface_hub import snapshot_download

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                               QWidget, QTextEdit, QPushButton, QLabel, QMessageBox, 
                               QProgressBar, QComboBox, QCheckBox, QGroupBox, QTabWidget, 
                               QLineEdit, QFileDialog)
from PySide6.QtCore import Qt, QThread, Signal, Slot

# === Файл настроек ===
CONFIG_FILE = "settings.json"
DEFAULT_MODEL_REPO = "santhosh/madlad400-3b-ct2"

LANGUAGES = {
    "Русский": "ru", "English": "en", "German": "de", "French": "fr",
    "Spanish": "es", "Ukrainian": "uk", "Italian": "it", "Chinese": "zh"
}

# === КЛАСС ДЛЯ РАБОТЫ С НАСТРОЙКАМИ ===
class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"model_path": os.getcwd(), "default_lang": "English"}

    @staticmethod
    def save(data):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

# === ДВИЖОК ===
class TranslatorEngine:
    def __init__(self):
        self.translator = None
        self.sp = None
        self.loaded_path = None

    def load(self, model_path):
        # Если уже загружено то же самое, не тратим время
        if self.translator and self.loaded_path == model_path:
            return True, "Модель уже загружена"

        try:
            sp_path = os.path.join(model_path, "sentencepiece.model")
            model_bin = os.path.join(model_path, "model.bin")
            
            if not os.path.exists(sp_path) or not os.path.exists(model_bin):
                return False, "Файлы модели не найдены"
            
            self.sp = spm.SentencePieceProcessor()
            self.sp.load(sp_path)
            self.translator = ctranslate2.Translator(model_path, device="cpu", intra_threads=0)
            self.loaded_path = model_path
            return True, "Модель успешно загружена"
        except Exception as e:
            return False, str(e)

    def translate(self, text, target_lang_code, beam_size=1):
        if not self.translator: return "Ошибка: Модель не загружена"
        try:
            input_text = f"<2{target_lang_code}> {text}"
            source_tokens = self.sp.encode_as_pieces(input_text)
            results = self.translator.translate_batch(
                [source_tokens], beam_size=beam_size, max_decoding_length=300
            )
            return self.sp.decode(results[0].hypotheses[0])
        except Exception as e:
            return f"Error: {e}"

engine = TranslatorEngine()

# === ПОТОКИ ===
class LoaderThread(QThread):
    finished_signal = Signal(bool, str)
    def __init__(self, path):
        super().__init__()
        self.path = path
    def run(self):
        success, msg = engine.load(self.path)
        self.finished_signal.emit(success, msg)

class TranslateThread(QThread):
    result_signal = Signal(str, float)
    def __init__(self, text, code, beam):
        super().__init__()
        self.text, self.code, self.beam = text, code, beam
    def run(self):
        start = time.time()
        res = engine.translate(self.text, self.code, self.beam)
        self.result_signal.emit(res, time.time() - start)

class DownloaderThread(QThread):
    """Качает модель с HuggingFace"""
    finished_signal = Signal(bool, str)
    
    def __init__(self, target_folder):
        super().__init__()
        self.target_folder = target_folder

    def run(self):
        try:
            snapshot_download(
                repo_id=DEFAULT_MODEL_REPO,
                local_dir=self.target_folder,
                local_dir_use_symlinks=False,
                resume_download=True
            )
            self.finished_signal.emit(True, "Скачивание завершено!")
        except Exception as e:
            self.finished_signal.emit(False, f"Ошибка скачивания: {e}")

# === GUI ===
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Translator Pro (MADLAD-3B)")
        self.resize(750, 600)
        self.apply_styles()
        
        # Загрузка конфига
        self.config = ConfigManager.load()
        
        # Основной виджет - ТАБЫ
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Создаем вкладки
        self.tab_translate = QWidget()
        self.tab_settings = QWidget()
        
        self.setup_translate_ui()
        self.setup_settings_ui()
        
        self.tabs.addTab(self.tab_translate, "🌐 Переводчик")
        self.tabs.addTab(self.tab_settings, "⚙️ Настройки и Модель")

        # Пробуем загрузить модель при старте
        self.check_and_load_model()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #fff; }
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #333; padding: 8px 20px; color: #aaa; }
            QTabBar::tab:selected { background: #444; color: #fff; border-bottom: 2px solid #007ACC; }
            QTextEdit, QLineEdit { background: #3b3b3b; border: 1px solid #555; padding: 5px; color: #fff; border-radius: 4px;}
            QPushButton { background: #007ACC; padding: 8px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #005A9E; }
            QPushButton:disabled { background: #444; color: #888; }
            QComboBox { background: #3b3b3b; border: 1px solid #555; padding: 4px; color: white; }
            QComboBox QAbstractItemView { background: #3b3b3b; color: white; selection-background-color: #007ACC; }
            QLabel { font-size: 13px; }
            QGroupBox { border: 1px solid #555; margin-top: 10px; padding-top: 10px; font-weight: bold; }
        """)

    # --- ВКЛАДКА 1: ПЕРЕВОД ---
    def setup_translate_ui(self):
        layout = QVBoxLayout(self.tab_translate)
        
        # Панель управления
        top_layout = QHBoxLayout()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        top_layout.addWidget(QLabel("Цель:"))
        top_layout.addWidget(self.lang_combo)
        
        self.auto_switch = QCheckBox("Авто-язык")
        self.auto_switch.setChecked(True)
        top_layout.addWidget(self.auto_switch)
        
        top_layout.addStretch()
        
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["⚡ Турбо (Beam=1)", "⚖️ Баланс (Beam=2)", "🧠 Качество (Beam=4)"])
        top_layout.addWidget(QLabel("Режим:"))
        top_layout.addWidget(self.speed_combo)
        layout.addLayout(top_layout)

        # Ввод/Вывод
        layout.addWidget(QLabel("Исходный текст:"))
        self.input_text = QTextEdit()
        self.input_text.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.input_text)
        
        self.btn_translate = QPushButton("ПЕРЕВЕСТИ")
        self.btn_translate.clicked.connect(self.start_translate)
        self.btn_translate.setFixedHeight(45)
        layout.addLayout(self.create_btn_layout(self.btn_translate))
        
        layout.addWidget(QLabel("Результат:"))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet("background-color: #222;")
        layout.addWidget(self.output_text)
        
        self.status_bar = QLabel("Ожидание...")
        layout.addWidget(self.status_bar)

    def create_btn_layout(self, btn):
        l = QHBoxLayout()
        l.addWidget(btn)
        return l

    # --- ВКЛАДКА 2: НАСТРОЙКИ ---
    def setup_settings_ui(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setSpacing(15)
        
        # Группа выбора пути
        gb_path = QGroupBox("Путь к папке с моделью")
        l_path = QVBoxLayout()
        
        path_controls = QHBoxLayout()
        self.path_edit = QLineEdit(self.config.get("model_path", ""))
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.setStyleSheet("background: #555;")
        self.btn_browse.clicked.connect(self.browse_folder)
        
        path_controls.addWidget(self.path_edit)
        path_controls.addWidget(self.btn_browse)
        l_path.addLayout(path_controls)
        
        # Индикатор статуса модели
        self.lbl_model_status = QLabel("Статус неизвестен")
        self.lbl_model_status.setStyleSheet("font-weight: bold; color: gray;")
        l_path.addWidget(self.lbl_model_status)
        
        # Кнопка применить
        self.btn_apply = QPushButton("Сохранить путь и Загрузить")
        self.btn_apply.clicked.connect(self.check_and_load_model)
        l_path.addWidget(self.btn_apply)
        
        gb_path.setLayout(l_path)
        layout.addWidget(gb_path)

        # Группа скачивания
        gb_down = QGroupBox("Скачивание модели (Интернет)")
        l_down = QVBoxLayout()
        l_down.addWidget(QLabel(f"Если модели нет, нажмите скачать.\nБудет скачано ~2.9 Гб с {DEFAULT_MODEL_REPO}"))
        
        self.btn_download = QPushButton("СКАЧАТЬ МОДЕЛЬ")
        self.btn_download.setStyleSheet("background-color: #D32F2F;")
        self.btn_download.clicked.connect(self.start_download)
        l_down.addWidget(self.btn_download)
        
        self.progress_down = QProgressBar()
        self.progress_down.setTextVisible(False)
        self.progress_down.hide()
        l_down.addWidget(self.progress_down)
        
        gb_down.setLayout(l_down)
        layout.addWidget(gb_down)
        
        layout.addStretch()

    # --- ЛОГИКА ---
    def browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Выбрать папку модели", self.path_edit.text())
        if d:
            self.path_edit.setText(d)

    def check_and_load_model(self):
        path = self.path_edit.text().strip()
        if not path:
            self.set_model_status(False, "Путь не указан")
            return

        # Сохраняем в конфиг
        self.config["model_path"] = path
        ConfigManager.save(self.config)
        
        # Блокируем интерфейс
        self.btn_translate.setEnabled(False)
        self.btn_translate.setText("Загрузка...")
        self.status_bar.setText("Инициализация движка...")
        
        # Запускаем поток загрузки
        self.loader = LoaderThread(path)
        self.loader.finished_signal.connect(self.on_model_loaded)
        self.loader.start()

    @Slot(bool, str)
    def on_model_loaded(self, success, msg):
        self.set_model_status(success, msg)
        if success:
            self.btn_translate.setEnabled(True)
            self.btn_translate.setText("ПЕРЕВЕСТИ")
            self.status_bar.setText("Готов к работе")
        else:
            self.btn_translate.setText("Модель не готова")

    def set_model_status(self, success, text):
        self.lbl_model_status.setText(text)
        color = "#4CAF50" if success else "#F44336" # Green / Red
        self.lbl_model_status.setStyleSheet(f"font-weight: bold; color: {color};")

    def start_download(self):
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Ошибка", "Выберите папку, куда качать!")
            return
            
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
                QMessageBox.warning(self, "Ошибка", "Не могу создать папку!")
                return

        reply = QMessageBox.question(self, "Скачивание", f"Начать скачивание в:\n{path}?\nЭто займет время.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return

        self.btn_download.setEnabled(False)
        self.progress_down.setRange(0, 0) # Бесконечный прогресс
        self.progress_down.show()
        self.lbl_model_status.setText("Идет скачивание... Не закрывайте программу!")
        
        self.downloader = DownloaderThread(path)
        self.downloader.finished_signal.connect(self.on_download_finished)
        self.downloader.start()

    @Slot(bool, str)
    def on_download_finished(self, success, msg):
        self.progress_down.hide()
        self.btn_download.setEnabled(True)
        QMessageBox.information(self, "Статус", msg)
        if success:
            self.check_and_load_model()

    def on_text_changed(self):
        if not self.auto_switch.isChecked(): return
        text = self.input_text.toPlainText()
        if not text: return
        has_ru = bool(re.search('[а-яА-Я]', text))
        curr = self.lang_combo.currentText()
        if has_ru and curr != "English": self.lang_combo.setCurrentText("English")
        elif not has_ru and curr != "Русский" and curr == "English": self.lang_combo.setCurrentText("Русский")

    def start_translate(self):
        text = self.input_text.toPlainText().strip()
        if not text: return
        
        beam = [1, 2, 4][self.speed_combo.currentIndex()]
        target = LANGUAGES[self.lang_combo.currentText()]
        
        self.btn_translate.setEnabled(False)
        self.status_bar.setText("Перевод...")
        
        self.worker = TranslateThread(text, target, beam)
        self.worker.result_signal.connect(self.on_result)
        self.worker.start()

    @Slot(str, float)
    def on_result(self, text, t):
        self.output_text.setPlainText(text)
        self.btn_translate.setEnabled(True)
        self.status_bar.setText(f"Готово за {t:.2f} сек")
        def closeEvent(self, event):
        # Если потоки еще работают — убиваем их перед выходом, чтобы не было ошибки
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.terminate()
            self.loader.wait()
        
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            
        if hasattr(self, 'downloader') and self.downloader.isRunning():
            self.downloader.terminate()
            self.downloader.wait()
            
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())