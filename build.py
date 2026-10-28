"""Build locally. This script never pushes tags, uploads assets or publishes releases."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description='Build the Windows desktop package locally')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--mitmdump',type=Path,help='Official mitmdump executable matching the pinned provenance')
    group.add_argument('--query-only',action='store_true',help='Explicitly omit the HTTPS engine')
    args=parser.parse_args()
    if sys.platform!='win32':parser.error('Build the desktop EXE on Windows.')
    if args.mitmdump:
        if not args.mitmdump.is_file():parser.error('The supplied mitmdump file is missing.')
        provenance=json.loads((ROOT/'third_party/mitmproxy.json').read_text(encoding='utf-8-sig'))
        if hashlib.sha256(args.mitmdump.read_bytes()).hexdigest()!=provenance['mitmdump_sha256']:
            parser.error('mitmdump SHA-256 does not match the pinned official engine.')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed',
                    '--name','gdmu-dorm-monitor','--paths',str(ROOT/'launcher'),
                    '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build/work'),
                    '--specpath',str(ROOT/'build/spec'),str(ROOT/'launcher/launcher.pyw')],cwd=ROOT,check=True)
    output=ROOT/'dist/gdmu-dorm-monitor'
    app=output/'app';app.mkdir(exist_ok=True)
    for source in (ROOT/'app').glob('*.py'):shutil.copy2(source,app/source.name)
    for name in ('.env.example','LICENSE','THIRD_PARTY_NOTICES.md'):shutil.copy2(ROOT/name,output/name)
    shutil.copytree(ROOT/'third_party',output/'third_party',dirs_exist_ok=True)
    shutil.copy2(ROOT/'docs/USER_GUIDE.md',output/'内置同步说明.md')
    if args.mitmdump:
        runtime=output/'runtime/https';runtime.mkdir(parents=True,exist_ok=True)
        shutil.copy2(args.mitmdump,runtime/'mitmdump.exe')
        shutil.copy2(ROOT/'third_party/licenses/mitmproxy-LICENSE.txt',runtime/'LICENSE-mitmproxy.txt')
    print(output)
    if args.query_only:print('Query-only build: not a complete embedded-sync release.')

if __name__=='__main__':main()
