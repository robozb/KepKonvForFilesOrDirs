import tkinter as tk
from tkinterdnd2 import TkinterDnD, DND_FILES
import subprocess
import os

class App(TkinterDnD.Tk):
    def __init__(self, script_path):
        super().__init__()
        self.script_path = script_path  # A script, amit meg szeretnél hívni
        self.title("Kep konv. drag & drop file handler")
        
        # Ablakméret és pozíció visszaállítása az előző indításból
        self.load_window_settings()

        self.file_list = []

        # Dinamikusan méretezhető Drag-and-Drop Area
        self.label = tk.Label(self, text="Drag and Drop files here", bg="lightgray", anchor="nw", justify="left")
        self.label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Dinamikusan méretezhető Start button
        self.start_button = tk.Button(self, text="Start", command=self.run_script_in_cmd)
        self.start_button.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

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
            tk.messagebox.showwarning("No Files", "Please drag and drop files first.")
            return

        # Prepare the argument list for the script, joining the files as arguments
        command = f'python "{self.script_path}" ' + " ".join([f'"{file}"' for file in self.file_list])

        try:
            # Run the script in a new command window
            subprocess.Popen(f'start cmd /K {command}', shell=True)
            tk.messagebox.showinfo("Success", "Script executed successfully in command window!")
        except subprocess.CalledProcessError as e:
            tk.messagebox.showerror("Error", f"An error occurred: {e}")
        except Exception as e:
            tk.messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def on_closing(self):
        # Ablak méretének és pozíciójának elmentése
        self.save_window_settings()
        self.destroy()

    def load_window_settings(self):
        """Ablakméret és pozíció betöltése az előző sessionből."""
        if os.path.exists("window_settings.txt"):
            with open("window_settings.txt", "r") as f:
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
        with open("window_settings.txt", "w") as f:
            f.write(f"{width},{height},{x},{y}")

if __name__ == "__main__":
    script_path = "D:\\_KepKonvForFilesOrDirs\\KepKonvForFilesOrDirs.py"  # Itt add meg a script elérési útját

    app = App(script_path)
    app.mainloop()
