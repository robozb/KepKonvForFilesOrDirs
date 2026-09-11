import tkinter as tk
from tkinter import messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
import subprocess
import os
import sys


def get_app_dir():
    """Az alkalmazas sajat mappaja - .py-kent es .exe-kent (PyInstaller) is helyes."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

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
