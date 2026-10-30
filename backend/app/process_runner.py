"""Fixed Python worker supervision, wall-clock cancellation and Windows Job limits."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


class WindowsJob:
    """Kill-on-close job: 256 MiB process memory, 30 CPU seconds, one process.

    The worker receives its input only after successful assignment. Fail closed
    on a Windows host where the OS job cannot be established.
    """
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IOCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            process.kill()
            raise RuntimeError("Could not create the bounded Windows ML job.")
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x0002 | 0x0008 | 0x0100 | 0x2000
        limits.BasicLimitInformation.PerProcessUserTimeLimit = 30 * 10_000_000
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.ProcessMemoryLimit = 256 * 1024 * 1024
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
            kernel.CloseHandle(handle)
            process.kill()
            raise RuntimeError("Could not enforce the bounded Windows ML job.")
        self.handle, self.kernel = handle, kernel

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _unix_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))


class ProcessRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.processes = {}
        self.cancelled = set()

    def cancel(self, job_id):
        with self.lock:
            self.cancelled.add(job_id)
            process = self.processes.get(job_id)
            if process and process.poll() is None:
                process.kill()
                return True
        return False

    def close(self):
        with self.lock:
            for process in self.processes.values():
                if process.poll() is None:
                    process.kill()

    def run(self, job_id, payload: bytes, timeout=60):
        if len(payload) > 16_000_000:
            raise ValueError("Training input exceeds the fixed cap.")
        worker = Path(__file__).with_name("ml_worker.py").resolve()
        # Child environment contains no API keys, session values or parent secrets.
        environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
        environment.update(PYTHONIOENCODING="utf-8", PYTHONHASHSEED="42", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"preexec_fn": _unix_limits}
        # A Windows venv launcher can spawn the real interpreter; use the
        # known base interpreter directly so the single-process Job cap holds.
        interpreter = getattr(sys, "_base_executable", sys.executable)
        process = subprocess.Popen([interpreter, "-I", str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=str(worker.parent), env=environment, **kwargs)
        job = WindowsJob(process)
        with self.lock:
            self.processes[job_id] = process
            if job_id in self.cancelled:
                process.kill()
        started = time.monotonic()
        try:
            output, errors = process.communicate(payload, timeout=timeout)
            if len(output) > 2_000_000 or len(errors) > 100_000:
                raise ValueError("Training output exceeded its cap.")
            if process.returncode:
                # Worker exposes only sanitized controlled exceptions in JSON;
                # do not return stderr, environment or machine paths to a user.
                import json
                try:
                    message = json.loads(output).get("error", "Training process failed or was cancelled.")
                except (ValueError, UnicodeError):
                    message = "Training process failed, exceeded its OS limit or was cancelled."
                raise ValueError(message)
            return output, {"worker_pid": process.pid, "wall_seconds": round(time.monotonic() - started, 4),
                            "separate_process": True, "memory_limit_mib": 256, "cpu_seconds_limit": 30,
                            "wall_seconds_limit": timeout, "native_artifact_only": True,
                            "network_adapter": False, "os_network_sandbox": False}
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate(timeout=5)
            raise ValueError("Training exceeded its fixed wall-clock budget and was terminated.") from exc
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            job.close()
            with self.lock:
                self.processes.pop(job_id, None)
                self.cancelled.discard(job_id)
