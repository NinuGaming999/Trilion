"""Live CPU / RAM / disk / GPU readings for the dashboard. No extra dependencies; never raises."""
import ctypes
import os
import shutil
import subprocess
import threading
import time

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("sullAvailExtendedVirtual", ctypes.c_uint64)]


class SysMon:
    def __init__(self, interval=2.0):
        self.data = {"cpu": 0.0, "ram": 0.0, "disk": 0.0, "gpu": None, "vram": None, "vram_total": None,
                     "gpu_name": ""}
        self.interval = interval
        self._prev = None
        self._tick = 0
        self._started = False

    def start(self):
        if not self._started:
            self._started = True
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            self.sample()
            time.sleep(self.interval)

    def sample(self):
        for name, fn in (("cpu", self._cpu), ("ram", self._ram), ("disk", self._disk)):
            try:
                self.data[name] = max(0.0, min(100.0, float(fn())))
            except Exception:
                pass
        if self._tick % 2 == 0:
            self._gpu()
        self._tick += 1
        return self.data

    # ---- CPU ----
    def _cpu(self):
        if os.name == "nt":
            idle, kern, user = ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            cur = (idle.value, kern.value + user.value)
        else:
            with open("/proc/stat") as f:
                v = [int(x) for x in f.readline().split()[1:]]
            cur = (v[3] + v[4], sum(v))
        prev, self._prev = self._prev, cur
        if not prev or cur[1] == prev[1]:
            return self.data["cpu"]
        return 100.0 * (1 - (cur[0] - prev[0]) / (cur[1] - prev[1]))

    # ---- RAM ----
    def _ram(self):
        if os.name == "nt":
            m = _MemStatus()
            m.dwLength = ctypes.sizeof(_MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.dwMemoryLoad
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                info[k] = int(v.split()[0])
        return 100.0 * (1 - info["MemAvailable"] / info["MemTotal"])

    # ---- disk ----
    def _disk(self):
        root = (os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else "/"
        u = shutil.disk_usage(root)
        return 100.0 * u.used / u.total

    # ---- GPU (NVIDIA) ----
    def _gpu(self):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4,
                                 creationflags=NO_WINDOW).stdout.strip().splitlines()[0]
            util, used, total, name = [x.strip() for x in out.split(",", 3)]
            self.data.update(gpu=float(util), vram=float(used), vram_total=float(total), gpu_name=name)
        except Exception:
            self.data.update(gpu=None, vram=None, vram_total=None)
