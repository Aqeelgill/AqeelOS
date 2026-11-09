import shutil, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BASE_DIR, DB_PATH, DATA_DIR
out = BASE_DIR / 'data' / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S')
out.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists(): shutil.copy2(DB_PATH, out / DB_PATH.name)
if (DATA_DIR/'outputs').exists(): shutil.copytree(DATA_DIR/'outputs', out/'outputs', dirs_exist_ok=True)
print('Backup written to', out)
