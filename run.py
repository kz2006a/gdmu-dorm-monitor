from pathlib import Path
import runpy
import sys
ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'app'))
if __name__ == '__main__':
    runpy.run_path(str(ROOT / 'app/gdmu_desktop.pyw'), run_name='__main__')
