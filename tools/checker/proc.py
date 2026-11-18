"""Starting tools and examples with a time limit and an output limit.

Every process starts in its own process group (POSIX: a new session;
Windows: a new process group). On a timeout or when a stream goes over the
limit, the whole group is stopped: `killpg` on POSIX, `taskkill /T /F` on
Windows. Output is read while the process runs, so a program that prints
without end is stopped as soon as it goes over the limit.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass

_STILL_ACTIVE = 259


@dataclass
class ProcResult:
    started: bool
    returncode: int | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    overflow: str = ""       # "stdout" or "stderr" when that stream went over the limit
    duration_ms: int = 0
    error: str = ""          # why the process could not be started


def _group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        try:
            proc.kill()
        except OSError:
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run_process(argv, cwd, env, timeout: float, stdin: bytes | None = None,
                limit: int = 65536) -> ProcResult:
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            [str(a) for a in argv], cwd=cwd, env=env,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_group_kwargs(),
        )
    except OSError as exc:
        return ProcResult(started=False, error=f"{type(exc).__name__}: {exc}")

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    over: list = []
    over_event = threading.Event()
    lock = threading.Lock()

    def read(stream, key: str) -> None:
        buf = buffers[key]
        try:
            while True:
                chunk = stream.read1(65536)
                if not chunk:
                    break
                room = limit + 1 - len(buf)
                if room > 0:
                    buf.extend(chunk[:room])
                if len(buf) > limit:
                    with lock:
                        if not over:
                            over.append(key)
                    over_event.set()
                    break
        except (OSError, ValueError):
            pass

    readers = [
        threading.Thread(target=read, args=(proc.stdout, "stdout"), daemon=True),
        threading.Thread(target=read, args=(proc.stderr, "stderr"), daemon=True),
    ]
    for thread in readers:
        thread.start()

    if stdin is not None:
        def feed() -> None:
            try:
                proc.stdin.write(stdin)
                proc.stdin.close()
            except (OSError, ValueError):
                pass
        threading.Thread(target=feed, daemon=True).start()

    deadline = start + timeout
    timed_out = False
    while True:
        try:
            proc.wait(timeout=0.02)
            break
        except subprocess.TimeoutExpired:
            pass
        if over_event.is_set():
            kill_tree(proc)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            kill_tree(proc)
            break
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    if os.name != "nt":
        kill_tree(proc)  # members of the group that outlived the main process
    for thread in readers:
        thread.join(timeout=5)
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except OSError:
            pass
    if not over:
        for key in ("stdout", "stderr"):
            if len(buffers[key]) > limit:
                over.append(key)
                break
    return ProcResult(
        started=True,
        returncode=proc.returncode,
        stdout=bytes(buffers["stdout"][:limit]) if over else bytes(buffers["stdout"]),
        stderr=bytes(buffers["stderr"][:limit]) if over else bytes(buffers["stderr"]),
        timed_out=timed_out,
        overflow=over[0] if over else "",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def pid_alive(pid: int) -> bool:
    """True while process PID exists (used by self-tests of the timeout)."""
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == _STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
