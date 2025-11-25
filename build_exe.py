import PyInstaller.__main__
import os
import shutil

# Имя твоего скрипта с программой
SCRIPT_NAME = "main.py"
# Имя выходного exe
EXE_NAME = "NeuralTranslator"

def build():
    print("🚀 Начинаем сборку EXE...")
    
    # Аргументы для PyInstaller
    args = [
        SCRIPT_NAME,
        f'--name={EXE_NAME}',
        '--noconfirm',
        
        # --onedir (папка) лучше для отладки и запуска тяжелых либ
        # --onefile (один файл) удобнее юзеру, но распаковывается дольше при запуске
        '--onefile', 
        
        # Оконный режим (без черной консоли). 
        # УБЕРИ 'w', если хочешь видеть консоль для отладки ошибок!
        '--windowed', 
        
        # Скрытые импорты, которые PyInstaller часто теряет
        '--hidden-import=ctranslate2',
        '--hidden-import=sentencepiece',
        '--hidden-import=huggingface_hub',
        
        # Включаем совместимость с путями
        '--clean',
    ]
    
    PyInstaller.__main__.run(args)
    
    print("\n✅ Сборка завершена!")
    print(f"📁 Ищи файл в папке: dist/{EXE_NAME}.exe")

if __name__ == "__main__":
    # Сначала проверим, установлен ли PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("❌ Ошибка: PyInstaller не установлен.")
        print("👉 Запусти: pip install pyinstaller")
        exit()
        
    build()