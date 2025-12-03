import sys
import os
import re
import ctypes
import time
import pyperclip
import logging
from ctypes import wintypes

# Импорт библиотеки глобальных хоткеев
from global_hotkeys import register_hotkeys, start_checking_hotkeys, stop_checking_hotkeys

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                               QWidget, QTextEdit, QPushButton, QLabel, QMessageBox, 
                               QProgressBar, QComboBox, QCheckBox, QGroupBox, QTabWidget, 
                               QLineEdit, QFileDialog, QSystemTrayIcon, QMenu)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QIcon, QAction

import logger
import translator_engine as te

# === ЛОГИ ===
logging.basicConfig(
    filename='debug.log', 
    level=logging.DEBUG, 
    format='%(asctime)s - %(message)s',
    filemode='w'
)

def log_debug(msg):
    print(msg) 
    logging.debug(msg)

myappid = 'neural.translator.pro.v1'
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

# ==========================================
# === WinAPI & MSAA (COM) DEFINITIONS ======
# ==========================================

VK_MENU = 0x12    # Alt
VK_CONTROL = 0x11 # Ctrl
VK_C = 0x43       # C
VK_V = 0x56       # V
KEYEVENTF_KEYUP = 0x0002

OBJID_CARET = -8
S_OK = 0
STATE_SYSTEM_INVISIBLE = 0x00008000
CHILDID_SELF = 0
VT_I4 = 3

# --- VARIANT Structure for COM ---
class VARIANT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("lVal", ctypes.c_long),
                    ("vt", ctypes.c_ushort)]
    _fields_ = [("vt", ctypes.c_ushort),
                ("wReserved1", ctypes.c_ushort),
                ("wReserved2", ctypes.c_ushort),
                ("wReserved3", ctypes.c_ushort),
                ("_u", _U)]

# --- IAccessible Interface Definition ---
# Нам нужен только get_accState, но vtable требует правильного порядка методов
COMMETHOD = ctypes.WINFUNCTYPE

class IAccessibleVtbl(ctypes.Structure):
    _fields_ = [
        # IUnknown
        ("QueryInterface", ctypes.c_void_p),
        ("AddRef", ctypes.c_void_p),
        ("Release", ctypes.c_void_p),
        # IDispatch
        ("GetTypeInfoCount", ctypes.c_void_p),
        ("GetTypeInfo", ctypes.c_void_p),
        ("GetIDsOfNames", ctypes.c_void_p),
        ("Invoke", ctypes.c_void_p),
        # IAccessible
        ("get_accParent", ctypes.c_void_p),
        ("get_accChildCount", ctypes.c_void_p),
        ("get_accChild", ctypes.c_void_p),
        ("get_accName", ctypes.c_void_p),
        ("get_accValue", ctypes.c_void_p),
        ("get_accDescription", ctypes.c_void_p),
        ("get_accRole", ctypes.c_void_p),
        # Index 14: get_accState
        ("get_accState", COMMETHOD(ctypes.HRESULT, ctypes.c_void_p, VARIANT, ctypes.POINTER(VARIANT))),
    ]

class IAccessible(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.POINTER(IAccessibleVtbl))]

class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]

IID_IAccessible = GUID(
    0x618736e0, 0x3c3d, 0x11cf, 
    (ctypes.c_ubyte * 8)(0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71)
)

class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT)
    ]

KNOWN_EDIT_CLASSES = [
    "Edit", "RichEdit", "RichEdit20A", "RichEdit20W", "TEdit", "TMemo", 
    "ConsoleWindowClass", "TextBox", "Scintilla"
]

class InputSimulator:
    """Класс для надежной эмуляции нажатий через WinAPI"""
    @staticmethod
    def press_key(vk_code):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    @staticmethod
    def release_key(vk_code):
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    @staticmethod
    def release_modifiers():
        InputSimulator.release_key(VK_MENU)
        InputSimulator.release_key(VK_CONTROL)
        InputSimulator.release_key(0x10)
    @staticmethod
    def send_ctrl_c():
        InputSimulator.release_modifiers()
        time.sleep(0.05)
        InputSimulator.press_key(VK_CONTROL)
        InputSimulator.press_key(VK_C)
        time.sleep(0.05)
        InputSimulator.release_key(VK_C)
        InputSimulator.release_key(VK_CONTROL)
    @staticmethod
    def send_ctrl_v():
        InputSimulator.release_modifiers()
        time.sleep(0.05)
        InputSimulator.press_key(VK_CONTROL)
        InputSimulator.press_key(VK_V)
        time.sleep(0.05)
        InputSimulator.release_key(VK_V)
        InputSimulator.release_key(VK_CONTROL)

class MainWindow(QMainWindow):
    action_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Translator Pro")
        self.resize(850, 650)
        
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(icon_path):
            self.app_icon = QIcon(icon_path)
            self.setWindowIcon(self.app_icon)
        else:
            self.app_icon = QIcon()

        self.apply_styles()
        self.config = te.ConfigManager.load()
        
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

        logger.setup_logger()
        logger.global_signals.log_signal.connect(self.append_log)
        
        self.action_signal.connect(self.run_smart_action_gui)
        
        self.check_and_load_model()
        self.init_tray()
        
        self.init_hotkeys()
        
        if self.is_admin():
            log_debug("ADMIN MODE: OK")
        else:
            log_debug("WARNING: NO ADMIN RIGHTS")

    def is_admin(self):
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
            QTabWidget::pane { border: 1px solid #333; background: #1e1e1e; top: -1px; }
            QTabBar::tab { background: #252526; color: #888; padding: 8px 25px; border: 1px solid #333; border-bottom: none; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:hover { background: #2d2d2d; color: #ccc; }
            QTabBar::tab:selected { background: #1e1e1e; color: #fff; border-top: 2px solid #007ACC; font-weight: bold; }
            QTextEdit, QLineEdit { background-color: #252526; border: 1px solid #3e3e42; color: #f0f0f0; padding: 5px; border-radius: 2px; }
            QTextEdit:focus, QLineEdit:focus { border: 1px solid #007ACC; }
            QPushButton { background-color: #007ACC; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #0062a3; }
            QPushButton:pressed { background-color: #005a9e; }
            QPushButton:disabled { background-color: #333; color: #666; }
            QComboBox { background-color: #252526; border: 1px solid #3e3e42; padding: 5px; color: white; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #252526; color: white; selection-background-color: #007ACC; }
            QCheckBox { color: #e0e0e0; spacing: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; background: #252526; border: 1px solid #3e3e42; border-radius: 3px; }
            QCheckBox::indicator:checked { background-color: #007ACC; border: 1px solid #007ACC; }
            QGroupBox { border: 1px solid #3e3e42; margin-top: 20px; padding-top: 15px; font-weight: bold; color: #ccc; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QProgressBar { border: 1px solid #3e3e42; text-align: center; background: #1e1e1e; }
            QProgressBar::chunk { background-color: #007ACC; }
        """)

    def setup_translate_ui(self):
        l = QVBoxLayout(self.tab_translate)
        l.setSpacing(10)
        top = QHBoxLayout()
        self.lang = QComboBox()
        self.lang.addItems(te.LANGUAGES.keys())
        self.lang.setMinimumWidth(150)
        top.addWidget(QLabel("Язык назначения:"))
        top.addWidget(self.lang)
        self.auto = QCheckBox("Авто-переключение (RU ⇄ EN)")
        self.auto.setChecked(True)
        top.addWidget(self.auto)
        top.addStretch()
        self.speed = QComboBox()
        self.speed.addItems(["Турбо (Быстро)", "Баланс (Норма)", "Качество (Медленно)"])
        top.addWidget(QLabel("Режим:"))
        top.addWidget(self.speed)
        l.addLayout(top)
        self.inp = QTextEdit()
        self.inp.setPlaceholderText("Введите текст или нажмите Alt+1 для вставки из буфера...")
        self.inp.textChanged.connect(self.on_text_change)
        l.addWidget(self.inp)
        self.btn = QPushButton("ПЕРЕВЕСТИ ТЕКСТ")
        self.btn.setMinimumHeight(45)
        self.btn.clicked.connect(self.start_tr)
        l.addWidget(self.btn)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setPlaceholderText("Здесь появится перевод...")
        self.out.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333;")
        l.addWidget(self.out)
        self.stat = QLabel("Готов к работе")
        self.stat.setStyleSheet("color: #666; font-size: 12px;")
        l.addWidget(self.stat, alignment=Qt.AlignRight)

    def setup_settings_ui(self):
        l = QVBoxLayout(self.tab_settings)
        l.setSpacing(20)
        gb = QGroupBox("Расположение модели")
        gl = QVBoxLayout()
        hl = QHBoxLayout()
        self.path_ed = QLineEdit(self.config.get("model_path", ""))
        self.br_btn = QPushButton("...")
        self.br_btn.setFixedWidth(40)
        self.br_btn.clicked.connect(self.browse)
        hl.addWidget(self.path_ed)
        hl.addWidget(self.br_btn)
        gl.addLayout(hl)
        self.lbl_st = QLabel("Статус: Проверка...")
        gl.addWidget(self.lbl_st)
        self.load_btn = QPushButton("Загрузить модель")
        self.load_btn.clicked.connect(self.check_and_load_model)
        gl.addWidget(self.load_btn)
        gb.setLayout(gl)
        l.addWidget(gb)
        
        gb_sys = QGroupBox("Системные настройки")
        gl_sys = QVBoxLayout()
        self.tray_check = QCheckBox("Сворачивать в трей при закрытии")
        self.tray_check.setChecked(self.config.get("minimize_to_tray", False))
        self.tray_check.toggled.connect(self.save_tray_setting)
        gl_sys.addWidget(self.tray_check)
        gb_sys.setLayout(gl_sys)
        l.addWidget(gb_sys)
        
        gb2 = QGroupBox("Загрузка из интернета")
        gl2 = QVBoxLayout()
        self.dl_btn = QPushButton("СКАЧАТЬ МОДЕЛЬ")
        self.dl_btn.setStyleSheet("background-color: #204a87;") 
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
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setStyleSheet("background-color: #0c0c0c; color: #00ff00; font-family: Consolas, monospace; font-size: 13px; border: 1px solid #333;")
        l.addWidget(self.logs)
        h = QHBoxLayout()
        clr = QPushButton("Очистить консоль")
        clr.setStyleSheet("background-color: #444;")
        clr.clicked.connect(self.logs.clear)
        h.addWidget(clr)
        l.addLayout(h)

    def save_tray_setting(self, checked):
        self.config["minimize_to_tray"] = checked
        te.ConfigManager.save(self.config)

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.app_icon)
        tray_menu = QMenu()
        action_show = QAction("Открыть окно", self)
        action_show.triggered.connect(self.show_normal)
        tray_menu.addAction(action_show)
        tray_menu.addSeparator()
        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self.force_quit)
        tray_menu.addAction(action_quit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_click)

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_normal()

    def show_normal(self):
        self.show()
        self.setWindowState(Qt.WindowActive)
        self.activateWindow()
        
    def force_quit(self):
        try: stop_checking_hotkeys()
        except: pass
        QApplication.quit()

    # --- GLOBAL HOTKEYS ---
    def init_hotkeys(self):
        log_debug("Запуск GlobalHotKeys...")
        try:
            bindings = [
                [["alt", "1"], None, self.on_ghk_triggered]
            ]
            register_hotkeys(bindings)
            start_checking_hotkeys()
            log_debug("GlobalHotKeys запущен (Alt+1).")
        except Exception as e:
            log_debug(f"Ошибка GHK: {e}")

    def on_ghk_triggered(self):
        log_debug(">>> GLOBAL HOTKEY: Alt+1 <<<")
        self.action_signal.emit()

    # === ДЕТАЛЬНАЯ ПРОВЕРКА КУРСОРА (WINAPI + MSAA STATE) ===
    def get_window_class(self, hwnd):
        length = 256
        buff = ctypes.create_unicode_buffer(length)
        ctypes.windll.user32.GetClassNameW(hwnd, buff, length)
        return buff.value

    def get_window_title(self, hwnd):
        length = 256
        buff = ctypes.create_unicode_buffer(length)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length)
        return buff.value

    def has_text_caret(self):
        """
        Проверка поля ввода с учетом "невидимых" курсоров в браузерах.
        """
        try:
            foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not foreground_hwnd: return False
                
            fg_title = self.get_window_title(foreground_hwnd)
            fg_class = self.get_window_class(foreground_hwnd)
            log_debug(f"DEBUG: Active Window: '{fg_title}' | Class: '{fg_class}'")

            # --- СПОСОБ 1: Стандартный WinAPI (Notepad, etc) ---
            foreground_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(foreground_hwnd, None)
            current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

            attached = False
            if foreground_thread_id != current_thread_id:
                attached = ctypes.windll.user32.AttachThreadInput(current_thread_id, foreground_thread_id, True)
            
            try:
                gui_info = GUITHREADINFO()
                gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
                success = ctypes.windll.user32.GetGUIThreadInfo(foreground_thread_id, ctypes.byref(gui_info))
                
                if success:
                    if gui_info.hwndCaret:
                        log_debug(f"DEBUG: Native Caret FOUND (HWND: {gui_info.hwndCaret})")
                        return True
                    
                    if gui_info.hwndFocus:
                        focus_class = self.get_window_class(gui_info.hwndFocus)
                        for cls in KNOWN_EDIT_CLASSES:
                            if cls.lower() in focus_class.lower():
                                log_debug(f"DEBUG: Detected input by class '{focus_class}'")
                                return True
            finally:
                if attached:
                    ctypes.windll.user32.AttachThreadInput(current_thread_id, foreground_thread_id, False)

            # --- СПОСОБ 2: MSAA с проверкой STATE (Браузеры) ---
            ptr = ctypes.POINTER(IAccessible)()
            res = ctypes.windll.oleacc.AccessibleObjectFromWindow(
                foreground_hwnd, 
                OBJID_CARET, 
                ctypes.byref(IID_IAccessible), 
                ctypes.byref(ptr)
            )
            
            if res == S_OK and ptr:
                # Объект курсора есть, но нужно проверить, ВИДИМ ЛИ ОН
                varChild = VARIANT()
                varChild.vt = VT_I4
                varChild._u.lVal = CHILDID_SELF
                
                varState = VARIANT()
                
                # Вызываем get_accState (индекс 14 в VTable)
                hr = ptr.contents.lpVtbl.contents.get_accState(ptr, varChild, ctypes.byref(varState))
                
                if hr == S_OK and varState.vt == VT_I4:
                    state = varState._u.lVal
                    log_debug(f"DEBUG: MSAA Caret State: {state} (Hex: {hex(state)})")
                    
                    # Проверяем флаг STATE_SYSTEM_INVISIBLE (0x8000)
                    if state & STATE_SYSTEM_INVISIBLE:
                        log_debug("DEBUG: Caret exists but is INVISIBLE -> Not an input field.")
                        return False
                    else:
                        log_debug("DEBUG: Caret exists and is VISIBLE -> Input field detected.")
                        return True
                
                # Освобождаем объект
                ptr.contents.lpVtbl.contents.Release(ptr)
            else:
                log_debug(f"DEBUG: MSAA Caret check failed or no object.")

            return False

        except Exception as e:
            log_debug(f"DEBUG: Exception in has_text_caret: {e}")
            return False

    # === УМНАЯ ЛОГИКА ===
    @Slot()
    def run_smart_action_gui(self):
        log_debug("--- ACTION START ---")
        
        InputSimulator.release_modifiers()
        time.sleep(0.1)

        pyperclip.copy("") 
        
        log_debug("Sending Ctrl+C via WinAPI...")
        InputSimulator.send_ctrl_c()
        
        text = ""
        for i in range(5): 
            time.sleep(0.1)
            text = pyperclip.paste()
            if text: break
        
        if not text:
            log_debug("FAIL: Буфер пуст.")
            return

        log_debug(f"Текст получен: {len(text)} симв.")
        
        is_editable = self.has_text_caret()
        log_debug(f"Editable (Smart Check): {is_editable}")

        if is_editable:
            self.translate_and_replace(text)
        else:
            self.translate_and_show(text)

    def translate_and_show(self, text):
        log_debug("Mode: Show Window")
        self.show_normal()
        self.inp.setPlainText(text)
        self.start_tr()

    def translate_and_replace(self, text):
        log_debug("Mode: Replace Inline")
        
        target_lang_name = self.lang.currentText()
        target_code = te.LANGUAGES[target_lang_name]
        
        if self.auto.isChecked():
            has_ru = bool(re.search('[а-яА-Я]', text))
            if has_ru: target_code = "en"
            else: target_code = "ru"

        try:
            res = te.engine.translate(text, target_code, beam_size=1)
            
            if res and not res.startswith("Error"):
                pyperclip.copy(res)
                time.sleep(0.1)
                log_debug("Sending Ctrl+V via WinAPI...")
                InputSimulator.send_ctrl_v()
            else:
                log_debug("Translation failed.")
        except Exception as e:
            log_debug(f"Replace error: {e}")

    # === UI ЛОГИКА ===
    @Slot(str)
    def append_log(self, text):
        if not text: return
        self.logs.append(text.strip()) 

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Выбор папки", self.path_ed.text())
        if d: self.path_ed.setText(d)

    def check_and_load_model(self):
        p = self.path_ed.text().strip()
        if not p: return
        self.config["model_path"] = p
        te.ConfigManager.save(self.config)
        self.btn.setEnabled(False)
        self.stat.setText("Загрузка...")
        self.loader = te.LoaderThread(p)
        self.loader.finished_signal.connect(self.on_load_done)
        self.loader.start()

    @Slot(bool, str)
    def on_load_done(self, s, m):
        self.lbl_st.setText(m)
        self.lbl_st.setStyleSheet(f"color: {'#0F0' if s else '#F00'}; font-weight: bold;")
        if s:
            self.btn.setEnabled(True)
            self.stat.setText("Модель готова")
        else:
            self.btn.setText("Ошибка загрузки")

    def dl_start(self):
        p = self.path_ed.text().strip()
        if not p: return
        self.dl_btn.setEnabled(False)
        self.prog.setRange(0,0)
        self.prog.show()
        self.dl = te.DownloaderThread(p)
        self.dl.finished_signal.connect(self.on_dl_done)
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
        tg = te.LANGUAGES[self.lang.currentText()]
        self.btn.setEnabled(False)
        self.stat.setText("Перевод...")
        self.worker = te.TranslateThread(t, tg, bm)
        self.worker.result_signal.connect(self.on_tr_done)
        self.worker.start()

    @Slot(str, float)
    def on_tr_done(self, txt, tm):
        self.out.setPlainText(txt)
        self.btn.setEnabled(True)
        self.stat.setText(f"Время перевода: {tm:.2f} сек")

    def closeEvent(self, e):
        should_minimize = self.config.get("minimize_to_tray", False)
        if self.tray_icon.isVisible() and should_minimize:
            e.ignore()
            self.hide()
            self.tray_icon.showMessage("Translator", "Свернуто в трей", QSystemTrayIcon.Information, 1000)
        else:
            try: stop_checking_hotkeys()
            except: pass
            e.accept()
            QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())