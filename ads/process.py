"""有界原生工具执行；POSIX 超时同时停止同组子进程。"""
import os
import signal
import subprocess


def execute(argv, *, cwd, stdout, stderr, timeout):
    process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr,
                               stdin=subprocess.DEVNULL, start_new_session=os.name == 'posix')
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise
