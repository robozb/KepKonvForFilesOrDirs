import os
import sys
import subprocess

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

def convert_image(src_file, dest_file, szelesseg, magassag, minoseg, mod):
    # Create parent directory for dest_file if it does not exist
    dest_dir = os.path.dirname(dest_file)
    os.makedirs(dest_dir, exist_ok=True)
    
    print(f"Feldolgozás: {src_file} -> {dest_file}")

    if mod == "n":
        subprocess.run([
            "magick", "convert", src_file, "-auto-orient", 
            "-thumbnail", f"{szelesseg}x{magassag}>", "-quality", str(minoseg), dest_file
        ])
    else:
        subprocess.run([
            "magick", src_file, "-auto-orient", 
            "-resize", f"{szelesseg}x{magassag}^^", "-quality", str(minoseg), 
            "-gravity", "center", "-extent", f"{szelesseg}x{magassag}", dest_file
        ])

def process_directory(directory, global_prefix, global_suffix, szelesseg, magassag, minoseg, mod, formatum):
    for file in os.listdir(directory):
        if file.lower().endswith('.jpg'):
            filepath = os.path.join(directory, file)
            file_dir = os.path.dirname(filepath)
            output_dir = os.path.join(file_dir, "opt-webp-or-jpg")
            prefix, suffix = get_prefix_suffix(file_dir, global_prefix, global_suffix)
            filename = os.path.splitext(os.path.basename(filepath))[0]
            output_file = os.path.join(output_dir, f"{prefix}{filename}{suffix}.{formatum}")
            convert_image(filepath, output_file, szelesseg, magassag, minoseg, mod)

def main():
    # Echo arguments
    print("ARGS start")
    print(" ".join(sys.argv[1:]))
    print("ARGS stop")


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

    # Set mod
    mod = get_input("\nVálassza ki a modot (n = normal(default), c = crop): ", default="n")
    if mod not in ["n", "c"]:
        mod = "n"
    else:
        print("cover (vigyázz: upscale lehetséges!)")
    print(f"Kiválasztott mód: {mod}")

    # Set formatum
    formatum = get_input("\nVálassza ki a formatumot (w = webp(default), j = jpg): ", default="w")
    if formatum not in ["j"]:
        formatum = "webp"
    elif formatum == "j":
        formatum = "jpg"
    print(f"Kiválasztott formátum: {formatum} \n")

    # Process files or directories
    for filepath in sys.argv[1:]:
        if os.path.isdir(filepath):
            print("\n")
            process_directory(filepath, global_prefix, global_suffix, szelesseg, magassag, minoseg, mod, formatum)
            print("\n")
        elif os.path.isfile(filepath) and filepath.lower().endswith('.jpg'):
            file_dir = os.path.dirname(filepath)
            output_dir = os.path.join(file_dir, "opt-webp-or-jpg")
            prefix, suffix = get_prefix_suffix(file_dir, global_prefix, global_suffix)
            filename = os.path.splitext(os.path.basename(filepath))[0]
            output_file = os.path.join(output_dir, f"{prefix}{filename}{suffix}.{formatum}")
            convert_image(filepath, output_file, szelesseg, magassag, minoseg, mod)

    # Pause before exit
    input("Nyomjon meg egy gombot a kilépéshez...")

if __name__ == "__main__":
    main()
