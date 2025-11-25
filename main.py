import sys
import os
import time
import re  # Для поиска русских букв
import ctranslate2
import sentencepiece as spm
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                               QWidget, QTextEdit, QPushButton, QLabel, QMessageBox, 
                               QProgressBar, QComboBox, QCheckBox, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont

# === НАСТРОЙКИ ===
MODEL_PATH = r"D:\nn\models\translation\madlad400-3b-ct2"

# Словарь поддерживаемых языков (Название в GUI -> Код для MADLAD)
LANGUAGES = {
    "Русский": "ru",
    "English": "en",
    "German": "de",
    "French": "fr",
    "Spanish": "es",
    "Ukrainian": "uk"
}

class TranslatorEngine:
    def __init__(self, model_path):
        self.model_path = model_path
        self.translator = None
        self.sp = None
        self.error = None

    def load(self):
        try:
            sp_path = os.path.join(self.model_path, "sentencepiece.model")
            if not os.path.exists(sp_path):
                raise FileNotFoundError(f"Нет файла sentencepiece.model в {self.model_path}")
            
            self.sp = spm.SentencePieceProcessor()
            self.sp.load(sp_path)
            
            # intra_threads=4 — оптимально для обычных ПК
            self.translator = ctranslate2.Translator(self.model_path, device="cpu", intra_threads=4)
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def translate(self, text, target_lang_code):
        if not self.translator or not self.sp:
            return "Ошибка: Модель не готова."
        
        try:
            # Формируем тег, например <2en> или <2ru>
            # MADLAD сам поймет исходный язык, главное дать ему целевой тег
            input_text = f"<2{target_lang_code}> {text}"
            
            source_tokens = self.sp.encode_as_pieces(input_text)
            results = self.translator.translate_batch([source_tokens])
            target_tokens = results[0].hypotheses[0]
            
            return self.sp.decode(target_tokens)
        except Exception as e:
            return f"Error: {e}"

# Глобальный движок
engine = TranslatorEngine(MODEL_PATH)

# === ПОТОКИ ===

class LoaderThread(QThread):
    finished_signal = Signal(bool, str)
    def run(self):
        success = engine.load()
        msg = "Модель готова" if success else engine.error
        self.finished_signal.emit(success, msg)

class TranslateThread(QThread):
    result_signal = Signal(str, float)
    def __init__(self, text, target_code):
        super().__init__()
        self.text = text
        self.target_code = target_code

    def run(self):
        start = time.time()
        res = engine.translate(self.text, self.target_code)
        elapsed = time.time() - start
        self.result_signal.emit(res, elapsed)

# === ИНТЕРФЕЙС ===

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Translator (MADLAD-3B)")
        self.resize(700, 600)
        
        # Стилизация
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: #ffffff; }
            QTextEdit { background-color: #3b3b3b; color: #ffffff; border: 1px solid #555; border-radius: 5px; font-size: 14px; padding: 5px; }
            QLabel { color: #aaaaaa; font-weight: bold; }
            QPushButton { background-color: #4CAF50; color: white; border-radius: 5px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #555; color: #888; }
            QComboBox { background-color: #3b3b3b; color: white; padding: 5px; border: 1px solid #555; border-radius: 3px; }
            QCheckBox { color: #ddd; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 1. Верхняя панель (Настройки перевода)
        top_panel = QHBoxLayout()
        
        top_panel.addWidget(QLabel("Перевести В:"))
        
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        self.lang_combo.setCurrentText("Русский") # По умолчанию
        top_panel.addWidget(self.lang_combo)

        top_panel.addStretch()
        
        # Чекбокс авто-определения
        self.auto_switch_cb = QCheckBox("Авто-выбор языка")
        self.auto_switch_cb.setChecked(True) # Включено по умолчанию
        self.auto_switch_cb.setToolTip("Если включено: при вводе кириллицы цель меняется на English, иначе на Русский")
        top_panel.addWidget(self.auto_switch_cb)

        main_layout.addLayout(top_panel)

        # 2. Поле ввода
        main_layout.addWidget(QLabel("ИСХОДНЫЙ ТЕКСТ:"))
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Введите текст здесь...")
        self.input_text.textChanged.connect(self.on_text_changed) # Следим за вводом
        main_layout.addWidget(self.input_text)

        # 3. Кнопка и прогресс
        btn_layout = QHBoxLayout()
        self.btn_translate = QPushButton("ЗАГРУЗКА ДВИЖКА...")
        self.btn_translate.setFixedHeight(45)
        self.btn_translate.setEnabled(False)
        self.btn_translate.clicked.connect(self.start_translation)
        btn_layout.addWidget(self.btn_translate)
        
        main_layout.addLayout(btn_layout)
        
        self.progress = QProgressBar()
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        main_layout.addWidget(self.progress)

        # 4. Поле вывода
        main_layout.addWidget(QLabel("РЕЗУЛЬТАТ:"))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet("background-color: #252526; color: #eee;")
        main_layout.addWidget(self.output_text)

        # Статус бар
        self.status_label = QLabel("Инициализация...")
        self.statusBar().addWidget(self.status_label)

        # Запуск загрузки
        self.loader = LoaderThread()
        self.loader.finished_signal.connect(self.on_loaded)
        self.loader.start()

    @Slot(bool, str)
    def on_loaded(self, success, msg):
        if success:
            self.btn_translate.setText("ПЕРЕВЕСТИ")
            self.btn_translate.setEnabled(True)
            self.status_label.setText("Движок готов.")
        else:
            self.btn_translate.setText("ОШИБКА")
            QMessageBox.critical(self, "Fatal Error", f"{msg}\n\nCheck path: {MODEL_PATH}")

    # === ЛОГИКА АВТО-ПЕРЕКЛЮЧЕНИЯ ЯЗЫКА ===
    def on_text_changed(self):
        if not self.auto_switch_cb.isChecked():
            return

        text = self.input_text.toPlainText()
        if not text:
            return

        # Простая эвристика: Есть ли русские буквы?
        has_cyrillic = bool(re.search('[а-яА-Я]', text))

        current_target = self.lang_combo.currentText()
        
        # Если есть русские буквы -> переводим НА English
        if has_cyrillic and current_target != "English":
            self.lang_combo.setCurrentText("English")
        
        # Если нет русских букв (латиница) -> переводим НА Русский
        elif not has_cyrillic and current_target != "Русский":
            # Не переключаем, если уже выбран другой язык (например Немецкий)
            # Переключаем на Русский только если сейчас стоит Английский
            if current_target == "English":
                self.lang_combo.setCurrentText("Русский")

    def start_translation(self):
        text = self.input_text.toPlainText().strip()
        if not text:
            return

        target_lang_name = self.lang_combo.currentText()
        target_code = LANGUAGES[target_lang_name]

        self.btn_translate.setEnabled(False)
        self.progress.show()
        self.status_label.setText(f"Перевожу в {target_lang_name}...")

        self.worker = TranslateThread(text, target_code)
        self.worker.result_signal.connect(self.on_result)
        self.worker.start()

    @Slot(str, float)
    def on_result(self, text, elapsed):
        self.output_text.setPlainText(text)
        self.btn_translate.setEnabled(True)
        self.progress.hide()
        self.status_label.setText(f"Готово ({elapsed:.2f} сек)")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())