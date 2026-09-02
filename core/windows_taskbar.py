import os
import sys
import ctypes
from ctypes import wintypes

TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', ctypes.c_ulong),
        ('Data2', ctypes.c_ushort),
        ('Data3', ctypes.c_ushort),
        ('Data4', ctypes.c_ubyte * 8)
    ]

class WindowsTaskbar:
    """Lightweight Win32 COM helper interface for ITaskbarList3 taskbar progress."""
    def __init__(self):
        self._taskbar_ptr = None
        if os.name == 'nt':
            try:
                ole32 = ctypes.windll.ole32
                ole32.CoInitialize(None)

                ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]
                ole32.IIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]

                clsid = GUID()
                iid = GUID()

                ole32.CLSIDFromString('{56FDF370-FD6D-11D0-958A-006097C51013}', ctypes.byref(clsid))
                ole32.IIDFromString('{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}', ctypes.byref(iid))

                CoCreateInstance = ctypes.WINFUNCTYPE(
                    ctypes.c_long,
                    ctypes.POINTER(GUID),
                    ctypes.c_void_p,
                    ctypes.c_ulong,
                    ctypes.POINTER(GUID),
                    ctypes.POINTER(ctypes.c_void_p)
                )(('CoCreateInstance', ole32))

                ptr = ctypes.c_void_p()
                res = CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(ptr))
                if res == 0 and ptr.value:
                    self._taskbar_ptr = ptr.value
                    vtable = ctypes.cast(self._taskbar_ptr, ctypes.POINTER(ctypes.c_void_p))
                    hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[3])
                    hr_init(self._taskbar_ptr)
            except Exception:
                self._taskbar_ptr = None

    def set_progress_state(self, hwnd, state=TBPF_NORMAL):
        if not self._taskbar_ptr or not hwnd:
            return
        try:
            vtable = ctypes.cast(self._taskbar_ptr, ctypes.POINTER(ctypes.c_void_p))
            set_state = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.c_int)(vtable[10])
            set_state(self._taskbar_ptr, int(hwnd), int(state))
        except Exception:
            pass

    def set_progress_value(self, hwnd, current, total=100):
        if not self._taskbar_ptr or not hwnd:
            return
        try:
            vtable = ctypes.cast(self._taskbar_ptr, ctypes.POINTER(ctypes.c_void_p))
            set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.c_uint64, ctypes.c_uint64)(vtable[9])
            set_value(self._taskbar_ptr, int(hwnd), int(current), int(total))
        except Exception:
            pass
