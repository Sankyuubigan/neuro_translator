import PyInstaller.__main__
import os
import shutil
import time
import subprocess

# Имя твоего скрипта и exe
SCRIPT_NAME = "main.py"
EXE_NAME = "NeuralTranslator"

def kill_process():
    """Убивает процесс, если он завис в памяти"""
    print(f"🔪 Проверяем, не запущен ли {EXE_NAME}.exe...")
    try:
        # Команда Windows для убийства процесса
        subprocess.run(f"taskkill /F /IM {EXE_NAME}.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1) # Даем винде время освободить файл
    except Exception:
        pass

def clean_dist():
    """Удаляет старую папку dist, чтобы собрать начисто"""
    dist_path = "dist"
    if os.path.exists(dist_path):
        try:
            shutil.rmtree(dist_path)
            print("🧹 Старая папка dist удалена.")
        except PermissionError:
            print("❌ ОШИБКА: Не могу удалить старый exe. Закрой программу вручную!")
            return False
    return True

def build():
    kill_process()
    
    if not clean_dist():
        return

    print("🚀 Начинаем сборку EXE...")
    
    args = [
        SCRIPT_NAME,
        f'--name={EXE_NAME}',
        '--noconfirm',
        '--onefile', 
        '--windowed', # Оконный режим
        '--hidden-import=ctranslate2',
        '--hidden-import=sentencepiece',
        '--hidden-import=huggingface_hub',
        '--clean',
        '--icon=NONE' # Если есть иконка, укажи путь (например --icon=app.ico)
    ]
    
    try:
        PyInstaller.__main__.run(args)
        print("\n✅ Сборка успешно завершена!")
        print(f"📁 Файл лежит тут: {os.path.abspath('dist')}\\{EXE_NAME}.exe")
    except Exception as e:
        print(f"\n❌ Ошибка сборки: {e}")

if __name__ == "__main__":
    build()