"""Mobilos készítési dátumok másolása egy újrahasznált ExifTool-folyamattal."""

import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime


def _stop_windows_children(parent_pid):
    """A saját ExifTool gyermekfolyamatait állítja le, WMI/taskkill nélkül."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return
    children = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        valid = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while valid:
            children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
            valid = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    descendants = [parent_pid]
    seen = {parent_pid}
    for pid in descendants:
        for child in children.get(pid, []):
            if child not in seen:
                seen.add(child)
                descendants.append(child)
    for pid in reversed(descendants[1:]):
        handle = kernel.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
        if handle:
            try:
                kernel.TerminateProcess(handle, 1)
            finally:
                kernel.CloseHandle(handle)


class ExifToolSession:
    """Soros parancsok; mindkét kimenet folyamatos olvasással, időkorláttal."""

    def __init__(self, executable=None, timeout=60):
        self.executable = executable or os.path.join(os.path.dirname(__file__), 'exiftool.exe')
        self.timeout = timeout
        self.process = None
        self.sequence = 0
        self.failure = None
        self.readers = []

    @staticmethod
    def _read(stream, target):
        try:
            for line in stream:
                target.put(line.rstrip('\r\n'))
        finally:
            target.put(None)

    def execute(self, args):
        if self.failure:
            raise RuntimeError(self.failure)
        args = [str(arg) for arg in args]
        if any('\n' in arg or '\r' in arg for arg in args):
            raise ValueError('Az ExifTool argumentuma nem tartalmazhat sortörést.')
        try:
            if self.process is None:
                self.process = subprocess.Popen(
                    [os.path.abspath(self.executable), '-stay_open', 'True', '-@', '-'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace', bufsize=1,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
                self.stdout = queue.Queue()
                self.stderr = queue.Queue()
                for stream, target in ((self.process.stdout, self.stdout),
                                       (self.process.stderr, self.stderr)):
                    reader = threading.Thread(target=self._read, args=(stream, target), daemon=True)
                    reader.start()
                    self.readers.append(reader)
            self.sequence += 1
            number = self.sequence
            status_prefix = f'photo-status-{number}='
            error_end = f'photo-stderr-{number}'
            command = ['-charset', 'filename=UTF8', *args,
                       '-echo3', status_prefix + '${status}',
                       '-echo4', error_end, f'-execute{number}']
            self.process.stdin.write('\n'.join(command) + '\n')
            self.process.stdin.flush()
            deadline = time.monotonic() + self.timeout

            def collect(source, marker):
                lines = []
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise queue.Empty
                    line = source.get(timeout=remaining)
                    if line is None:
                        raise RuntimeError('Az ExifTool váratlanul leállt.')
                    if line == marker:
                        return lines
                    lines.append(line)

            output = collect(self.stdout, f'{{ready{number}}}')
            errors = collect(self.stderr, error_end)
            status = next((line[len(status_prefix):] for line in output
                           if line.startswith(status_prefix)), None)
            output = [line for line in output if not line.startswith(status_prefix)]
            if status is None:
                raise RuntimeError('Az ExifTool nem adott vissza állapotkódot.')
        except (OSError, RuntimeError, queue.Empty) as exc:
            self.failure = ('Az ExifTool nem válaszolt időben.' if isinstance(exc, queue.Empty)
                            else str(exc))
            self.close()
            raise RuntimeError(self.failure) from exc
        if status != '0':
            raise RuntimeError('\n'.join(errors + output) or f'ExifTool állapot: {status}')
        return '\n'.join(output), '\n'.join(errors)

    def close(self):
        if self.process is None:
            return
        process = self.process
        try:
            if process.poll() is None:
                process.stdin.write('-stay_open\nFalse\n')
                process.stdin.flush()
                process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                # A Windows ExifTool-csomag külön gyerekfolyamatot indíthat.
                # Csak a szülő kilövése nyitva hagyná a pipe-okat és a gyereket.
                if os.name == 'nt':
                    try:
                        _stop_windows_children(process.pid)
                    except OSError:
                        pass
                if process.poll() is None:
                    process.kill()
            process.wait()
        finally:
            for reader in self.readers:
                reader.join(timeout=2)
            # Egy váratlanul árván maradt gyerek nem akaszthatja meg a bezárást.
            streams = [process.stdin]
            streams.extend(stream for stream, reader in zip(
                (process.stdout, process.stderr), self.readers[-2:]) if not reader.is_alive())
            for stream in streams:
                try:
                    stream.close()
                except OSError:
                    pass
            self.process = None


class PhotoDatePreserver:
    def __init__(self, enabled=True, executable=None):
        self.enabled = enabled
        self.session = ExifToolSession(executable)
        self.copied = self.missing = self.failed = self.local_timezone = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()

    def copy(self, src, dest):
        if not self.enabled:
            return False
        src, dest = os.path.abspath(src), os.path.abspath(dest)
        try:
            output, _ = self.session.execute([
                '-j', '-EXIF:DateTimeOriginal', '-EXIF:OffsetTimeOriginal',
                '-EXIF:SubSecTimeOriginal', src,
            ])
            metadata = json.loads(output)[0]
            if metadata.get('Error'):
                raise ValueError(metadata['Error'])
            original = metadata.get('DateTimeOriginal')
            if not original:
                self.missing += 1
                print(f'   [Dátum] Nincs EXIF készítési idő; nem állítottam be helyettesítő dátumot: {src}')
                return False
            offset = metadata.get('OffsetTimeOriginal', '')
            taken = datetime.strptime(original + offset,
                                      '%Y:%m:%d %H:%M:%S%z' if offset else '%Y:%m:%d %H:%M:%S')
            subsecond = str(metadata.get('SubSecTimeOriginal', ''))
            if subsecond.isdigit():
                taken = taken.replace(microsecond=int((subsecond + '000000')[:6]))
            timestamp = taken.timestamp()
            # Csak a dátumokat másoljuk: az auto-orient után nem állítjuk vissza az Orientation tagot.
            _, warnings = self.session.execute([
                '-overwrite_original', '-TagsFromFile', src,
                '-EXIF:DateTimeOriginal', '-EXIF:CreateDate', '-EXIF:ModifyDate',
                '-EXIF:OffsetTime*', '-EXIF:SubSecTime*', dest,
            ])
            if warnings:
                print(f'   [ExifTool] {warnings}')
            os.utime(dest, (os.stat(dest).st_atime, timestamp))
            self.copied += 1
            if not offset:
                self.local_timezone += 1
                if self.local_timezone == 1:
                    print('   [Dátum] Hiányzó időzónánál a fájl módosítási idejéhez '
                          'a számítógép helyi időzónáját használom. Az EXIF készítési idő változatlan.')
            return True
        except (RuntimeError, OSError, ValueError, KeyError, IndexError, OverflowError) as exc:
            self.failed += 1
            print(f'   [Dátum] Nem sikerült megőrizni a készítési időt: {src}: {exc}')
            return False

    def summary(self):
        if self.enabled:
            print(f'Dátummegőrzés: {self.copied} sikeres, {self.missing} készítési dátum nélkül, '
                  f'{self.failed} hibás; {self.local_timezone} képnél helyi időzóna.')
