import os
import sys
import subprocess
from datetime import datetime  # Importáljuk a datetime modult



def get_input(prompt, default=None):
    value = input(prompt)
    if not value and default is not None:
        value = default
    return value

def get_prefix_suffix(file_dir, global_prefix, global_suffix):
    # Check for prefix in the file's directory if global prefix is not set
    if global_prefix:
        prefix = global_prefix
    else:
        prefix_path = os.path.join(file_dir, 'prefix.txt')
        if os.path.exists(prefix_path):
            with open(prefix_path) as f:
                prefix = f.read().strip() + '-'
        else:
            prefix = ''

    # Check for suffix in the file's directory if global suffix is not set
    if global_suffix:
        suffix = global_suffix
    else:
        suffix_path = os.path.join(file_dir, 'suffix.txt')
        if os.path.exists(suffix_path):
            with open(suffix_path) as f:
                suffix = '-' + f.read().strip()
        else:
            suffix = ''

    return prefix, suffix

def convert_image(src_file, dest_file, szelesseg, magassag, minoseg, mod, message, background_color="white",preserve_dates=True):
    dest_dir = os.path.dirname(dest_file)
    os.makedirs(dest_dir, exist_ok=True)

    # Ellenőrizze a forrásfájl kiterjesztését
    src_extension = os.path.splitext(src_file)[1].lower()

    # Ha a forrás PNG, akkor adjuk hozzá a .png kiterjesztést a célfájlnévhez
    if src_extension == ".png":
        dest_file = os.path.splitext(dest_file)[0] + ".png" + os.path.splitext(dest_file)[1]
        print(f"PNG forrás - hozzáadott kiterjesztés: {dest_file}")

    print(f"Feldolgozás: {message} {src_file} -> {dest_file}")

    if mod == "n":
        params = [
            "magick", "convert", src_file, "-auto-orient",
            "-thumbnail", f"{szelesseg}x{magassag}>", "-quality", str(minoseg)
        ]

        if dest_file.lower().endswith(".avif"):
            params.extend([
                "-define", "heic:compression=av1",
                "-define", "heic:speed=6",
                "-define", f"heic:quality={minoseg}"
            ])

        params.append(dest_file)
        subprocess.run(params)
    elif mod == "c":
        subprocess.run([
            "magick", src_file, "-auto-orient",
            "-resize", f"{szelesseg}x{magassag}^^", "-quality", str(minoseg),
            "-gravity", "center", "-extent", f"{szelesseg}x{magassag}", dest_file
        ])
    elif mod == "t":
        subprocess.run([
            "magick", src_file, "-auto-orient",
            "-resize", f"{szelesseg}x{magassag}", "-background", background_color,
            "-gravity", "center", "-extent", f"{szelesseg}x{magassag}", "-quality", str(minoseg), dest_file
        ])
    else:
        print(f"Ismeretlen mód: {mod}")
    # Dátumok átmásolása
    if preserve_dates:
       set_all_dates_from_file(src_file, dest_file)
        
def set_all_dates_from_file(src, dest):
    
    import datetime

    if dest.lower().endswith(".avif"):
        print("[Exiftool] ⚠️ Az AVIF fájlformátum nem támogatja az EXIF metaadatok írását. Dátum nem másolható.")
        return

    try:
        EXIFTOOL_PATH = r"exiftool.exe"
        src = os.path.normpath(src)
        dest = os.path.normpath(dest)

        # Fájlrendszerből olvassuk ki a pontos időt
        stat = os.stat(src)
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
        formatted = mtime.strftime("%Y:%m:%d %H:%M:%S")

        # Ezt az értéket írjuk be MINDEN mezőbe
        subprocess.run([
            EXIFTOOL_PATH,
            "-overwrite_original",
            f"-AllDates={formatted}",
            f"-DateTimeOriginal={formatted}",
            f"-CreateDate={formatted}",
            f"-ModifyDate={formatted}",
            f"-FileCreateDate={formatted}",
            f"-FileModifyDate={formatted}",
            dest
        ], check=True)

    except subprocess.CalledProcessError as e:
        print(f"[Exiftool] dátum másolás hiba: {e}")
    except Exception as e:
        print(f"[Exiftool] általános hiba: {e}")


"""
    1. „Létrehozva” ≠ mikor készült a kép
    Ez a fájlrendszer szerinti dátum, amikor ez a példány létrejött az adott mappában (pl. másoláskor).

    Ha C:-ről átmásolod F:-re, akkor másolás dátuma lesz a „létrehozás”, nem a fotó készítési ideje.

    2. „Módosítva” = tartalom utolsó módosítása
    Ha a fájl valaha át lett szerkesztve (akár iPhone, akár backup során), ez a dátum tükrözi azt.

    De ez is változhat másolás, mentés, backup során!

    3. „Hozzáférés” = mikor néztél rá
    Ez minden egyes megnyitásnál frissül. Ez tök haszontalan a valódi dátum szempontjából.

    4. A „Részletek” fül (EXIF) → az igazi időpont
    Oda menti a kamera az igazi dátumokat: DateTimeOriginal, CreateDate, ModifyDate

    Ezek nem látszanak az „Általános” fülön

     Na akkor: Milyen dátumot látunk az Explorerben?
    A lista nézet „Dátum” oszlopa (amit a fájllista tetején látsz):
    Fájltípus	„Dátum” mező jelentése
    📷 .JPG, .PNG, .MOV stb. (fénykép/video)	az EXIF DateTimeOriginal mezőt mutatja, ha van
    📄 más típusú fájl	a fájlrendszer szerinti „Módosítva” időt
    📄 .webp fájl	nincs EXIF támogatás → fájlrendszer „módosítva” dátum
    📌 Vagyis a „Dátum” oszlop nem a fájlrendszer szerinti „létrehozás” dátumát mutatja.
"""

     

def process_directory(directory, global_prefix, global_suffix, szelesseg, magassag, minoseg, mod, formatum, output_base_dir,preserve_dates=True):
    files = [f for f in os.listdir(directory) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    total_files = len(files)
    current_file = 0
    
    for file in files:
        filepath = os.path.join(directory, file)
        file_dir = os.path.dirname(filepath)
        
        if output_base_dir:
            output_dir = output_base_dir
        else:
            output_dir = os.path.join(file_dir, "opt-webp-or-jpg")
        
        prefix, suffix = get_prefix_suffix(file_dir, global_prefix, global_suffix)
        filename = os.path.splitext(os.path.basename(filepath))[0]
        output_file = os.path.join(output_dir, f"{prefix}{filename}{suffix}.{formatum}")
        
        current_file += 1
        convert_image(filepath, output_file, szelesseg, magassag, minoseg, mod, f"{current_file}/{total_files}",preserve_dates)

def main():

    if len(sys.argv) <= 1:
        # Kérdezzen meg egy mappát, ha nincs megadva parancssori argumentum
        directory = get_input("Adja meg a feldolgozandó mappát: ")
        if not directory or not os.path.isdir(directory):
            print("Érvénytelen mappa.")
            return
        sys.argv.append(directory)


    # Echo arguments
    print("ARGS start")
    print(" ".join(sys.argv[1:]))
    print("ARGS stop")

    # Set output base directory
    output_base_dir = get_input("\nAdja meg a cél mappát (vagy hagyja üresen): ")
    if output_base_dir:
        print(f"Kiválasztott cél mappa: {output_base_dir}")
    else:
        print("A konvertált fájlok az eredeti helyükön maradnak.")

    # Set global prefix
    global_prefix = get_input("\nAdja meg a globális prefixet (vagy hagyja üresen): ")
    if global_prefix:
        global_prefix = f"{global_prefix}-"
        print(f"Kiválasztott globális prefix: {global_prefix}")


    # Set global suffix
    global_suffix = get_input("\nAdja meg a globális suffixet (vagy hagyja üresen): ")
    if global_suffix:
        global_suffix = f"-{global_suffix}"
        print(f"Kiválasztott globális suffix: {global_suffix}")

    # Set szelesseg
    szelesseg = get_input("\nAdja meg a szeleseget(default:3840): ", default="3840")
    print(f"Kiválasztott szelesseg: {szelesseg}")

    # Set magassag
    magassag = get_input("\nAdja meg a magassagot(default:2160): ", default="2160")
    print(f"Kiválasztott magassag: {magassag}")

    # Set minoseg
    minoseg = get_input("\nAdja meg a minoseget (default:75): ", default="75")
    print(f"Kiválasztott minoseg: {minoseg}")
    
    # Kérdés a dátumok megőrzéséről
    preserve_input = get_input("\nMeg akarja őrizni az eredeti dátumokat? (i/n, default: i): ", default="i")
    preserve_dates = preserve_input.lower() == "i"    

    # Set mod
    mod = get_input("\nVálassza ki a modot (n = normal(default), c = crop, t = contain): ", default="n")
    if mod not in ["n", "c", "t"]:
        mod = "n"
    print(f"Kiválasztott mód: {mod}")
    
    # Set background color, ha "contain" mód van
    background_color = "white"  # alapértelmezett
    if mod == "t":
        background_color = get_input("\nAdja meg a háttér színét (pl. white, black, transparent,#gghh22) (default: white): ", default="white")
        print(f"Kiválasztott háttér színe: {background_color}")    

    # Set formatum
    formatum = get_input("\nVálassza ki a formátumot (w = webp (default), j = jpg, a = avif): ", default="w")
    if formatum == "j":
        formatum = "jpg"
    elif formatum == "a":
        formatum = "avif"
    else:
        formatum = "webp"

    print(f"Kiválasztott formátum: {formatum} \n")

    # Process files or directories
    for filepath in sys.argv[1:]:
        if os.path.isdir(filepath):
            print("\n")
            process_directory(filepath, global_prefix, global_suffix, szelesseg, magassag, minoseg, mod, formatum, output_base_dir,preserve_dates=True)
            print("\n")
        elif os.path.isfile(filepath) and filepath.lower().endswith(('.jpg', '.jpeg', '.png')):
            file_dir = os.path.dirname(filepath)
            
            if output_base_dir:
                output_dir = output_base_dir
            else:
                output_dir = os.path.join(file_dir, "opt-webp-or-jpg")
            
            prefix, suffix = get_prefix_suffix(file_dir, global_prefix, global_suffix)
            filename = os.path.splitext(os.path.basename(filepath))[0]
            output_file = os.path.join(output_dir, f"{prefix}{filename}{suffix}.{formatum}")
            convert_image(filepath, output_file, szelesseg, magassag, minoseg, mod, "",background_color, preserve_dates=True)

    # Pause before exit
    print("\nFeldolgozás vége: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    input("Nyomjon meg egy gombot a kilépéshez...")

if __name__ == "__main__":
    main()

