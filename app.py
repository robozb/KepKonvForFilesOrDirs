import tkinter as tk
from tkinter import messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
import subprocess
import os
import sys


RAW_COPY_SCRIPT = r"I:\AdatokrolAthelyezveIde\Képzés\1. Szakmai\Informatika\Win10\JPGAlapjanRAWCopy\JPGAlapjanRAWCopy.py"
KEPKONV_OUTPUT_DIR = "opt-webp-or-jpg"  # A KepKonvForFilesOrDirs.py alapértelmezett kimeneti almappája
SELECTION_DIR = "valogatas"


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

        # Gombsor: Start + script mappa megnyitása
        self.button_frame = tk.Frame(self)
        self.button_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
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

    def on_closing(self):
        # Ablak méretének és pozíciójának elmentése
        self.save_window_settings()
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
