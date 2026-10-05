import tkinter as tk
from tkinter import messagebox, filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES
import subprocess
import threading
import os
import re
import sys
from datetime import datetime


RAW_COPY_SCRIPT = r"I:\AdatokrolAthelyezveIde\Képzés\1. Szakmai\Informatika\Win10\JPGAlapjanRAWCopy\JPGAlapjanRAWCopy.py"
KEPKONV_OUTPUT_DIR = "opt-webp-or-jpg"  # A KepKonvForFilesOrDirs.py alapértelmezett kimeneti almappája
SELECTION_DIR = "valogatas"
WATCH_EXTENSIONS = ('.jpg', '.jpeg', '.png')  # A KepKonvForFilesOrDirs.py SUPPORTED_INPUTS-a
WATCH_INTERVAL_MS = 2000  # Ennyi időnként nézzük át a figyelt mappát
WATCH_FOLDER_FILE = "watch_folder.txt"  # Az utoljára figyelt mappa, az app mappájában
WATCH_LOG_FILE = "figyelo.log"  # A figyelő által indított konverziók teljes kimenete


def get_app_dir():
    """Az alkalmazas sajat mappaja - .py-kent es .exe-kent (PyInstaller) is helyes."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_faststone_exe():
    """FSViewer.exe helye: először a registry App Paths, utána a szokásos telepítési mappák."""
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\FSViewer.exe"
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, key_path) as key:
                    path = winreg.QueryValue(key, None)
                    if path and os.path.isfile(path):
                        return path
            except OSError:
                pass
    except ImportError:
        pass

    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base:
            path = os.path.join(base, "FastStone Image Viewer", "FSViewer.exe")
            if os.path.isfile(path):
                return path
    return None

class App(TkinterDnD.Tk):
    def __init__(self, script_path):
        super().__init__()
        self.script_path = os.path.abspath(script_path)  # A script, amit meg szeretnél hívni
        self.script_dir = os.path.dirname(self.script_path)
        self.settings_path = os.path.join(get_app_dir(), "window_settings.txt")
        self.title("Kep konv. drag & drop file handler")
        
        # Ablakméret és pozíció visszaállítása az előző indításból
        self.load_window_settings()

        self.file_list = []

        # Dinamikusan méretezhető Drag-and-Drop Area
        self.label = tk.Label(self, text="Drag and Drop files here", bg="lightgray", anchor="nw", justify="left")
        self.label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Mappafigyelő: a mappába kerülő új képeket az alapbeállításokkal konvertálja
        self.watch_frame = tk.Frame(self)
        self.watch_frame.grid(row=1, column=0, sticky="ew", padx=10)
        self.watch_frame.grid_columnconfigure(1, weight=1)

        tk.Label(self.watch_frame, text="Figyelt mappa:").grid(row=0, column=0, sticky="w")
        self.watch_dir_var = tk.StringVar(value=self.load_watch_folder())
        self.watch_entry = tk.Entry(self.watch_frame, textvariable=self.watch_dir_var)
        self.watch_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.watch_entry.drop_target_register(DND_FILES)
        self.watch_entry.dnd_bind('<<Drop>>', self.drop_watch_folder)

        # A mezőben lévő mappa megnyitása Intézőben (figyelés közben is használható)
        self.watch_open_button = tk.Button(
            self.watch_frame,
            text="📂",
            font=("Segoe UI Emoji", 10),
            command=self.open_watch_folder,
        )
        self.watch_open_button.grid(row=0, column=2, sticky="ns", padx=(5, 0))

        self.watch_browse_button = tk.Button(self.watch_frame, text="Tallózás...", command=self.browse_watch_folder)
        self.watch_browse_button.grid(row=0, column=3, sticky="ew", padx=(10, 0))

        self.watch_button = tk.Button(self.watch_frame, text="Figyelés indítása", width=18, command=self.toggle_watch)
        self.watch_button.grid(row=0, column=4, sticky="ew", padx=(10, 0))

        self.watch_status = tk.Label(self.watch_frame, text="Figyelés: kikapcsolva", anchor="w")
        self.watch_status.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(5, 0))

        self.watch_dir = None  # A figyelés közben használt mappa (nem a szerkeszthető mező)
        self.watch_job = None  # A következő after() hívás azonosítója
        self.watch_last_snapshot = None  # Az előző átnézés képei: {név: (méret, módosítás)}
        self.watch_done_snapshot = {}  # A legutóbbi konverzióba már bekerült állapot
        self.watch_worker = None  # A futó konverzió szála
        self.watch_result = None  # A szál ide teszi az eredményt, az átnézés olvassa ki

        # Gombsor: Start + script mappa megnyitása
        self.button_frame = tk.Frame(self)
        self.button_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        self.button_frame.grid_columnconfigure(0, weight=1)

        self.start_button = tk.Button(self.button_frame, text="Start", command=self.run_script_in_cmd)
        self.start_button.grid(row=0, column=0, sticky="ew")

        self.folder_button = tk.Button(
            self.button_frame,
            text="Script mappa",
            command=self.open_script_dir,
        )
        self.folder_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # Csak akkor aktív, ha pontosan egy elem lett behúzva, és az egy mappa
        self.faststone_button = tk.Button(
            self.button_frame,
            text="FastStone",
            command=self.open_in_faststone,
            state="disabled",
        )
        self.faststone_button.grid(row=0, column=2, sticky="ew", padx=(10, 0))

        # Bejelölve a FastStone indítása előtt létrehozza a "valogatas" almappát
        self.create_selection_var = tk.BooleanVar(value=False)
        self.create_selection_check = tk.Checkbutton(
            self.button_frame,
            text="Válogatás mappa létrehozása",
            variable=self.create_selection_var,
        )
        self.create_selection_check.grid(row=0, column=3, sticky="w", padx=(10, 0))

        self.raw_copy_button = tk.Button(
            self.button_frame,
            text="RAW másoló",
            command=self.open_raw_copy,
        )
        self.raw_copy_button.grid(row=0, column=4, sticky="ew", padx=(10, 0))

        # Ablak rácsbeállítás a dinamikus méretezéshez
        self.grid_rowconfigure(0, weight=1)  # A címke sorának növelése a rendelkezésre álló hely arányában
        self.grid_columnconfigure(0, weight=1)  # Az oszlop arányos növelése

        # Bind Drag-and-Drop event
        self.label.drop_target_register(DND_FILES)
        self.label.dnd_bind('<<Drop>>', self.drop_files)

        # Ablak bezárása előtti esemény megkötése
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def drop_files(self, event):
        # Clear the file list before each drag and drop
        self.file_list.clear()

        # Add the new files from the drag and drop event
        files = self.tk.splitlist(event.data)
        for file in files:
            self.file_list.append(file)

        # Update the label to show only the current dropped files
        self.label.config(text=f"Files:\n" + "\n".join(self.file_list))

        self.faststone_button.config(state="normal" if self.get_single_dir() else "disabled")

    def get_single_dir(self):
        """Visszaadja a mappát, ha pontosan egy elem van a listában és az mappa, különben None."""
        if len(self.file_list) == 1 and os.path.isdir(self.file_list[0]):
            return self.file_list[0]
        return None

    def get_base_dir(self):
        """Az eredeti (forrás) mappa: egy mappa esetén maga a mappa, fájloknál a közös szülőmappájuk.

        None, ha nincs behúzott elem, vagy a fájlok különböző mappákban vannak
        (ilyenkor a KepKonv is több kimeneti mappába ír).
        """
        single_dir = self.get_single_dir()
        if single_dir:
            return os.path.normpath(single_dir)
        parents = {os.path.normcase(os.path.dirname(os.path.abspath(f))) for f in self.file_list}
        if len(parents) != 1:
            return None
        return os.path.dirname(os.path.abspath(self.file_list[0]))

    def get_output_dir(self):
        """A KepKonv alapértelmezett kimeneti mappája (<forrás mappa>\\opt-webp-or-jpg)."""
        base_dir = self.get_base_dir()
        return os.path.join(base_dir, KEPKONV_OUTPUT_DIR) if base_dir else None

    def get_selection_dir(self):
        """A valogatas mappa a KepKonv kimenetén belül."""
        output_dir = self.get_output_dir()
        return os.path.join(output_dir, SELECTION_DIR) if output_dir else None

    def run_script_in_cmd(self):
        if not self.file_list:
            messagebox.showwarning("No Files", "Please drag and drop files first.")
            return

        # Prepare the argument list for the script, joining the files as arguments
        command = f'python "{self.script_path}" ' + " ".join([f'"{file}"' for file in self.file_list])

        try:
            # Run the script in a new command window
            subprocess.Popen(f'start cmd /K {command}', shell=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def open_script_dir(self):
        """A script mappájának megnyitása az Intézőben (a script helye alapján)."""
        if not os.path.isdir(self.script_dir):
            messagebox.showerror("Hiba", f"A mappa nem található:\n{self.script_dir}")
            return
        try:
            if os.path.isfile(self.script_path):
                # A scriptet kijelölve nyitjuk meg a mappát
                subprocess.Popen(["explorer", "/select,", os.path.normpath(self.script_path)])
            else:
                os.startfile(self.script_dir)
        except Exception as e:
            messagebox.showerror("Hiba", f"Nem sikerült megnyitni a mappát:\n{e}")

    def open_in_faststone(self):
        """A KepKonv kimeneti mappájának megnyitása FastStone Image Viewerben.

        Bejelölt jelölőnégyzetnél előtte létrehozza benne a valogatas mappát.
        """
        if not self.get_single_dir():
            messagebox.showwarning("Nincs mappa", "Pontosan egy mappát húzz be.")
            return
        output_dir = self.get_output_dir()
        if not os.path.isdir(output_dir):
            messagebox.showwarning(
                "Nincs kimenet",
                f"A KepKonv kimeneti mappája még nem létezik:\n{output_dir}\n\nElőbb futtasd a konvertálást (Start).",
            )
            return
        exe = find_faststone_exe()
        if not exe:
            messagebox.showerror("Hiba", "A FastStone Image Viewer (FSViewer.exe) nem található.")
            return
        if self.create_selection_var.get():
            try:
                os.makedirs(self.get_selection_dir(), exist_ok=True)
            except OSError as e:
                messagebox.showerror("Hiba", f"Nem sikerült létrehozni a valogatas mappát:\n{e}")
                return
        try:
            subprocess.Popen([exe, output_dir])
        except Exception as e:
            messagebox.showerror("Hiba", f"Nem sikerült elindítani a FastStone-t:\n{e}")

    def open_raw_copy(self):
        """A JPGAlapjanRAWCopy GUI indítása (a saját mappájából, hogy a config.ini-t megtalálja).

        A kép könyvtár a KepKonv kimenetében lévő valogatas mappa (ha létezik),
        a RAW könyvtár pedig az eredeti, behúzott forrás mappa.
        """
        if not os.path.isfile(RAW_COPY_SCRIPT):
            messagebox.showerror("Hiba", f"A script nem található:\n{RAW_COPY_SCRIPT}")
            return
        args = ["python", RAW_COPY_SCRIPT]
        base_dir = self.get_base_dir()
        if base_dir:
            selection_dir = self.get_selection_dir()
            if os.path.isdir(selection_dir):
                args += ["--jpg-dir", selection_dir]
            args += ["--raw-dir", base_dir]
        try:
            subprocess.Popen(
                args,
                cwd=os.path.dirname(RAW_COPY_SCRIPT),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            messagebox.showerror("Hiba", f"Nem sikerült elindítani a RAW másolót:\n{e}")

    def drop_watch_folder(self, event):
        if self.watch_dir:
            messagebox.showinfo("Figyelés fut", "A mappa cseréjéhez előbb állítsd le a figyelést.")
            return
        paths = self.tk.splitlist(event.data)
        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.watch_dir_var.set(os.path.normpath(paths[0]))
        else:
            messagebox.showwarning("Nincs mappa", "Egyetlen mappát húzz ide.")

    def open_watch_folder(self):
        folder = self.watch_dir_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("Nincs mappa", f"A mappa nem található:\n{folder}")
            return
        try:
            os.startfile(os.path.normpath(folder))
        except OSError as e:
            messagebox.showerror("Hiba", f"Nem sikerült megnyitni a mappát:\n{e}")

    def browse_watch_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self.watch_dir_var.get() or None,
            title="Figyelt mappa kiválasztása",
        )
        if folder:
            self.watch_dir_var.set(os.path.normpath(folder))

    def toggle_watch(self):
        if self.watch_dir:
            self.stop_watch()
        else:
            self.start_watch()

    def start_watch(self):
        """A mappa figyelésének indítása. Az első átnézés a még nem konvertált képeket is feldolgozza."""
        folder = self.watch_dir_var.get().strip()
        if not os.path.isdir(folder):
            messagebox.showwarning("Nincs mappa", f"A mappa nem található:\n{folder}")
            return
        if not os.path.isfile(self.script_path):
            messagebox.showerror("Hiba", f"A konverter script nem található:\n{self.script_path}")
            return
        self.watch_dir = os.path.normpath(folder)
        self.watch_last_snapshot = None
        self.watch_done_snapshot = {}
        self.save_watch_folder()
        self.watch_entry.config(state="disabled")
        self.watch_browse_button.config(state="disabled")
        self.watch_button.config(text="Figyelés leállítása")
        self.set_watch_status("várakozás új képekre")
        # Leállítás után még futhat az előző kör a konverzió végéig; nem indítunk mellé másikat
        if self.watch_job:
            self.after_cancel(self.watch_job)
        self.poll_watch_folder()

    def stop_watch(self):
        """Új konverziót nem indít; egy már futó konverzió befejeződik, az eredménye megjelenik."""
        self.watch_dir = None
        self.watch_entry.config(state="normal")
        self.watch_browse_button.config(state="normal")
        self.watch_button.config(text="Figyelés indítása")
        busy = self.watch_worker is not None and self.watch_worker.is_alive()
        self.set_watch_status("a futó konverzió még befejeződik" if busy else "")

    def set_watch_status(self, text):
        state = "Figyelés bekapcsolva" if self.watch_dir else "Figyelés kikapcsolva"
        self.watch_status.config(text=f"{state} – {text}" if text else state)

    @staticmethod
    def scan_watch_folder(folder):
        """A mappa közvetlen képei: {név: (méret, módosítás)}. Az almappákat (pl. a kimenetet) nem nézi."""
        snapshot = {}
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.name.lower().endswith(WATCH_EXTENSIONS):
                    continue
                try:
                    # Nem az entry.stat(): Windowson a könyvtárbejegyzés mérete íráskor késve frissül
                    stat = os.stat(entry.path)
                except OSError:
                    continue  # Közben törölték
                if os.path.isfile(entry.path):
                    snapshot[entry.name] = (stat.st_size, stat.st_mtime_ns)
        return snapshot

    def poll_watch_folder(self):
        """Időnkénti átnézés. Konverziót csak akkor indít, ha van új vagy megváltozott kép,
        és két egymást követő átnézésnél is változatlan (tehát a másolása befejeződött)."""
        self.watch_job = None
        self.collect_watch_result()
        busy = self.watch_worker is not None and self.watch_worker.is_alive()
        if not self.watch_dir:
            if busy:  # Leállítás után csak a futó konverzió eredményét várjuk meg
                self.watch_job = self.after(WATCH_INTERVAL_MS, self.poll_watch_folder)
            return
        try:
            snapshot = self.scan_watch_folder(self.watch_dir)
        except OSError as e:
            self.set_watch_status(f"a mappa nem olvasható: {e}")
        else:
            stable = snapshot == self.watch_last_snapshot
            self.watch_last_snapshot = snapshot
            changed = any(self.watch_done_snapshot.get(name) != info for name, info in snapshot.items())
            if stable and changed and not busy:
                self.start_watch_conversion(snapshot)
        self.watch_job = self.after(WATCH_INTERVAL_MS, self.poll_watch_folder)

    def start_watch_conversion(self, snapshot):
        # A már konvertált képeket a konverter kihagyja (létező célfájl), így csak az újak dolgozódnak fel.
        # Hibás képet újra akkor próbál, ha a mappában megint változás történik.
        self.watch_done_snapshot = snapshot
        self.watch_result = None
        self.set_watch_status("konvertálás folyamatban...")
        self.watch_worker = threading.Thread(
            target=self.run_watch_conversion, args=(self.watch_dir,), daemon=True
        )
        self.watch_worker.start()

    def run_watch_conversion(self, folder):
        """Háttérszálon fut: a konverter kérdések nélkül, az alapértékekkel, rejtett ablakban.
        Tkinter-hívás itt nincs, az eredményt a poll_watch_folder olvassa ki."""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            result = subprocess.run(
                ["python", self.script_path, "--auto", folder],
                cwd=self.script_dir,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            output = result.stdout + result.stderr
        except Exception as e:
            output = f"Nem sikerült elindítani a konvertert: {e}"
        try:
            # Mindig csak a legutóbbi futás kimenete marad meg
            with open(os.path.join(get_app_dir(), WATCH_LOG_FILE), "w", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {folder}\n\n{output}")
        except OSError:
            pass
        self.watch_result = output

    def collect_watch_result(self):
        output, self.watch_result = self.watch_result, None
        if output is None:
            return
        summary = re.search(r"Konverzió: (\d+) sikeres, (\d+) hibás", output)
        if summary:
            converted, failed = summary.groups()
            text = f"{converted} új kép konvertálva"
            if failed != "0":
                text += f", {failed} hibás (részletek: {WATCH_LOG_FILE})"
        else:
            text = f"a konverzió nem futott le (részletek: {WATCH_LOG_FILE})"
        self.set_watch_status(f"utolsó futás {datetime.now():%H:%M:%S}: {text}")

    def load_watch_folder(self):
        try:
            with open(os.path.join(get_app_dir(), WATCH_FOLDER_FILE), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def save_watch_folder(self):
        try:
            with open(os.path.join(get_app_dir(), WATCH_FOLDER_FILE), "w", encoding="utf-8") as f:
                f.write(self.watch_dir_var.get().strip())
        except OSError:
            pass

    def on_closing(self):
        # Ablak méretének és pozíciójának elmentése
        self.save_window_settings()
        self.save_watch_folder()
        self.destroy()

    def load_window_settings(self):
        """Ablakméret és pozíció betöltése az előző sessionből."""
        if os.path.exists(self.settings_path):
            with open(self.settings_path, "r") as f:
                data = f.read().split(',')
                self.geometry(f"{data[0]}x{data[1]}+{data[2]}+{data[3]}")
        else:
            self.geometry("600x400")  # Alapértelmezett méret

    def save_window_settings(self):
        """Ablakméret és pozíció mentése egy fájlba."""
        geometry = self.geometry()  # pl. "600x400+100+100"
        size, position = geometry.split('+', 1)
        width, height = size.split('x')
        x, y = position.split('+')
        with open(self.settings_path, "w") as f:
            f.write(f"{width},{height},{x},{y}")

if __name__ == "__main__":
    # A konverter script az app mellett van - dinamikusan állapítjuk meg
    script_path = os.path.join(get_app_dir(), "KepKonvForFilesOrDirs.py")

    app = App(script_path)
    app.mainloop()
