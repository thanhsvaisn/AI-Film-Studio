"""Portable Windows entry point for the bundled onedir executable."""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
os.environ['FILM_STUDIO_DATA'] = str(root / 'data')
os.environ['VOXCPM_MODEL_DIR'] = str(root / 'models' / 'VoxCPM2')
os.environ['HF_HOME'] = str(root / 'cache' / 'huggingface')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['PATH'] = str(root / 'bin') + os.pathsep + os.environ.get('PATH', '')
os.chdir(root)


def open_browser():
    time.sleep(2)
    webbrowser.open('http://127.0.0.1:8765')


if __name__ == '__main__':
    import uvicorn
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run('backend.app:app', host='127.0.0.1', port=8765, workers=1, log_level='warning')
