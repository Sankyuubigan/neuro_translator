import PyInstaller.__main__
import os
import shutil
import time
import subprocess
import sys

# Попытка импорта Pillow для конвертации
try:
    from PIL import Image
except ImportError:
    print("❌ ОШИБКА: Не установлена библиотека Pillow.")
    print("👉 Запусти: pip install Pillow")
    sys.exit(1)

SCRIPT_NAME = "main.py"
EXE_NAME = "NeuralTranslator"
PNG_ICON = "logo.png"
ICO_ICON = "logo.ico"

def kill_process():
    print(f"🔪 Проверяем процессы {EXE_NAME}...")
    try:
        subprocess.run(f"taskkill /F /IM {EXE_NAME}.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1) 
    except: pass

def clean_dist():
    if os.path.exists("dist"):
        try: shutil.rmtree("dist")
        except: pass
    if os.path.exists("build"):
        try: shutil.rmtree("build")
        except: pass

def prepare_icon():
    """Автоматически создает .ico из .png, если .ico нет"""
    abs_png = os.path.abspath(PNG_ICON)
    abs_ico = os.path.abspath(ICO_ICON)

    if not os.path.exists(abs_png):
        print(f"⚠️ ВНИМАНИЕ: Файл {PNG_ICON} не найден! Иконки не будет.")
        return None

    # Если ico уже есть - используем его, если нет - создаем из png
    if not os.path.exists(abs_ico):
        print(f"🔄 Конвертирую {PNG_ICON} в {ICO_ICON} для Windows...")
        try:
            img = Image.open(abs_png)
            # Сохраняем как ICO с разными размерами для лучшего качества
            img.save(abs_ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
            print("✅ Конвертация успешна.")
        except Exception as e:
            print(f"❌ Ошибка конвертации иконки: {e}")
            return None
    
    return abs_ico

def build():
    kill_process()
    clean_dist()

    print(f"🚀 Начинаем сборку...")
    
    # 1. Готовим иконку (PNG -> ICO)
    icon_path = prepare_icon()
    
    args = [
        SCRIPT_NAME,
        f'--name={EXE_NAME}',
        '--noconfirm',
        '--onefile', 
        '--windowed',
        '--hidden-import=ctranslate2',
        '--hidden-import=sentencepiece',
        '--hidden-import=huggingface_hub',
        '--clean',
    ]

    # Добавляем иконку EXE (если создалась)
    if icon_path:
        args.append(f'--icon={icon_path}')
        # Также добавляем сам PNG внутрь программы для GUI
        args.append(f'--add-data={os.path.abspath(PNG_ICON)};.')

    try:
        PyInstaller.__main__.run(args)
        print("\n✅ Сборка готова!")
        print(f"📁 EXE файл: {os.path.abspath('dist')}\\{EXE_NAME}.exe")
        
        # Удаляем временный ico файл, если хотим (сейчас оставил, чтобы не пересоздавать каждый раз)
        # if os.path.exists(ICO_ICON): os.remove(ICO_ICON)
        
    except Exception as e:
        print(f"\n❌ Ошибка PyInstaller: {e}")

if __name__ == "__main__":
    build()