"""Record real local availability. No fabricated Harbor/OpenCode integration claims."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def version(cmd):
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
        return {'exit_code':p.returncode,'output':(p.stdout or p.stderr).strip()[:320]}
    except Exception as exc:
        return {'error':str(exc)[:320]}

def main():
    programs={}
    for name in ('python3','node','chromium','docker','podman','harbor','opencode','playwright'):
        path=shutil.which(name)
        command = [path,'--version'] if path else None
        programs[name]={'installed':bool(path),'path':path,'version':version(command) if command else None}
    packages={}
    for name in ('playwright','pytest','openpyxl','harbor'):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    browser_binary={'status':'UNVERIFIED'}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            location=Path(playwright.chromium.executable_path)
            browser_binary={'path':str(location),'installed':location.is_file(),
                            'status':'BINARY_PRESENT_NOT_TESTED' if location.is_file() else 'BROWSER_BINARY_MISSING'}
    except Exception as exc:
        browser_binary={'status':'UNAVAILABLE','detail':str(exc)[:200]}
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'playwright_bundled_chromium':browser_binary,
            'os':platform.platform(), 'programs':programs,'python_packages':packages,
            'poc_decisions':{
              'HTTP_SQLite_XLSX':'TESTED: see calibration summary',
              'Playwright_runner':'NOT_VERIFIED: reference/full did not PASS; use permitted runner and --require-browser',
              'Playwright_test_agents_for_OpenCode':'NOT_TESTED: OpenCode binary and Node test-agent integration not available',
              'Harbor_adapter':'NOT_TESTED: Harbor and Docker/Podman absent; cannot claim isolated worker evaluation',
              'OpenCode_SDK_session_recovery':'NOT_TESTED: OpenCode CLI absent',
              'External_protected_CI':'NOT_IMPLEMENTED: local grader shares host filesystem'} }
    output=ROOT/'artifacts'/'tool-probe.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
