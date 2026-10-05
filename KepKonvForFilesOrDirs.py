import os
import sys
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
from datetime import datetime
from photo_dates import PhotoDatePreserver

# Egyszerre feldolgozott képek felső korlátja (a gép magszáma is korlátoz).
DEFAULT_WORKERS = 6
# Képenkénti ImageMagick pixelgyorsítótár-limit gigabájtban. Ez felső korlát,
# nem lefoglalás: az ImageMagick csak annyit használ, amennyi a képhez kell.
DEFAULT_MEMORY_LIMIT_GB = 15
# Kérdések nélküli futás az alapértékekkel (a GUI mappafigyelője használja).
AUTO_ARG = '--auto'
auto_mode = False



def get_input(prompt, default=None):
    if auto_mode:
        return default or ''
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

SUPPORTED_INPUTS = ('.jpg', '.jpeg', '.png')


@dataclass(frozen=True)
class ConversionJob:
    source: str
    destination: str


@dataclass
class BatchResult:
    converted: int = 0
    failed: int = 0
    skipped: int = 0


def output_path(src_file, dest_file):
    """A PNG névkiegészítés egyetlen közös helyen történik."""
    if os.path.splitext(src_file)[1].lower() == '.png':
        stem, extension = os.path.splitext(dest_file)
        return stem + '.png' + extension
    return dest_file


def _path_key(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _magick_command(src_file, dest_file, szelesseg, magassag, minoseg, mod,
                    background_color, thread_limit=None,
                    memory_limit_gb=DEFAULT_MEMORY_LIMIT_GB):
    params = ['magick']
    if thread_limit is not None:
        params += ['-limit', 'thread', str(thread_limit)]
    if memory_limit_gb:
        # A map limit a memórialimit kétszerese, ahogy az ImageMagick ajánlja.
        params += ['-limit', 'memory', f'{memory_limit_gb:g}GiB',
                   '-limit', 'map', f'{memory_limit_gb * 2:g}GiB']
    params += [src_file, '-auto-orient']
    if mod == "n":
        params += ['-thumbnail', f'{szelesseg}x{magassag}>', '-quality', str(minoseg)]
        if dest_file.lower().endswith(".avif"):
            params.extend([
                "-define", "heic:compression=av1",
                "-define", "heic:speed=6",
                "-define", f"heic:quality={minoseg}"
            ])

    elif mod == "c":
        params.extend([
            "-resize", f"{szelesseg}x{magassag}^", "-quality", str(minoseg),
            "-gravity", "center", "-extent", f"{szelesseg}x{magassag}"
        ])
    elif mod == "t":
        params.extend([
            "-resize", f"{szelesseg}x{magassag}", "-background", background_color,
            "-gravity", "center", "-extent", f"{szelesseg}x{magassag}", "-quality", str(minoseg)
        ])
    else:
        raise ValueError(f'Ismeretlen mód: {mod}')
    return params + [dest_file]


def _run_conversion(job, szelesseg, magassag, minoseg, mod, background_color,
                    thread_limit=None, memory_limit_gb=DEFAULT_MEMORY_LIMIT_GB):
    """Csak képkonverzió; nincs közös ExifTool-hívás vagy konzolírás a workerben.

    A részleges kimenet ideiglenes fájl, a publikálás nem ír felül létező célt.
    Az üres visszatérési érték sikert, a szöveg hibát jelent.
    """
    temp_path = None
    try:
        if _path_key(job.source) == _path_key(job.destination):
            return 'A célfájl azonos a forrással.'
        if os.path.lexists(job.destination):
            return 'A célfájl már létezik; nem írtam felül.'
        dest_dir = os.path.dirname(os.path.abspath(job.destination))
        os.makedirs(dest_dir, exist_ok=True)
        descriptor, temp_path = tempfile.mkstemp(
            prefix='.kepkonv-', suffix=os.path.splitext(job.destination)[1], dir=dest_dir)
        os.close(descriptor)
        command = _magick_command(job.source, temp_path, szelesseg, magassag,
                                  minoseg, mod, background_color, thread_limit,
                                  memory_limit_gb)
        result = subprocess.run(command, capture_output=True, text=True, errors='replace')
        if result.returncode != 0:
            return (result.stderr or result.stdout or f'ImageMagick hibakód: {result.returncode}').strip()
        if os.path.getsize(temp_path) == 0:
            return 'Az ImageMagick nem hozott létre képet.'
        if os.name == 'nt':
            os.rename(temp_path, job.destination)  # Windows: létező célnál hibát ad.
        else:
            os.link(temp_path, job.destination)  # Nem felülíró publikálás POSIX alatt is.
            os.unlink(temp_path)
        temp_path = None
        return ''
    except (OSError, ValueError) as exc:
        return str(exc)
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def convert_image(src_file, dest_file, szelesseg, magassag, minoseg, mod, message, background_color="white", preserve_dates=True, date_preserver=None):
    dest_file = output_path(src_file, dest_file)
    print(f"Feldolgozás: {message} {src_file} -> {dest_file}")
    error = _run_conversion(ConversionJob(src_file, dest_file), szelesseg, magassag,
                            minoseg, mod, background_color)
    if error:
        print(f'Hiba: {src_file}: {error}')
        return False
    if preserve_dates:
        set_all_dates_from_file(src_file, dest_file, date_preserver)
    return True


def set_all_dates_from_file(src, dest, date_preserver=None):
    """Készítési idő megőrzése EXIF-ben és fájl-módosítási időként.

    A létrehozási időt nem állítjuk. Hiányzó EXIF készítési időt nem
    helyettesítünk a forrásfájl módosítási idejével.
    """
    if date_preserver is not None:
        return date_preserver.copy(src, dest)
    with PhotoDatePreserver() as dates:
        return dates.copy(src, dest)


def plan_conversions(paths, global_prefix, global_suffix, formatum, output_base_dir):
    """Az egész bemenetre kiterjedő, determinisztikus névütközés-ellenőrzés."""
    sources, seen_sources, jobs, reserved, affixes = [], set(), [], set(), {}
    skipped = 0

    def skip(path, reason):
        nonlocal skipped
        skipped += 1
        print(f'Kihagyva: {path} — {reason}')

    for path in paths:
        path = os.path.abspath(path)
        try:
            if os.path.isdir(path):
                candidates = [os.path.join(path, name) for name in sorted(os.listdir(path), key=str.casefold)
                              if name.lower().endswith(SUPPORTED_INPUTS)]
            else:
                candidates = [path]
            for source in candidates:
                if not os.path.isfile(source) or not source.lower().endswith(SUPPORTED_INPUTS):
                    skip(source, 'nem támogatott vagy nem létező képfájl')
                    continue
                key = _path_key(source)
                if key in seen_sources:
                    skip(source, 'a bemenet már szerepel a feldolgozásban')
                    continue
                seen_sources.add(key)
                sources.append(source)
        except OSError as exc:
            skip(path, str(exc))

    for source in sources:
        try:
            directory = os.path.dirname(source)
            if directory not in affixes:
                affixes[directory] = get_prefix_suffix(directory, global_prefix, global_suffix)
            prefix, suffix = affixes[directory]
            output_dir = output_base_dir or os.path.join(directory, 'opt-webp-or-jpg')
            filename = os.path.splitext(os.path.basename(source))[0]
            destination = os.path.abspath(output_path(
                source, os.path.join(output_dir, f'{prefix}{filename}{suffix}.{formatum}')))
            key = _path_key(destination)
            if key in seen_sources:
                skip(source, f'a cél egy bemeneti fájl: {destination}')
            elif os.path.lexists(destination):
                skip(source, f'a cél már létezik: {destination}')
            elif key in reserved:
                skip(source, f'egy korábbi bemenetnek ugyanez a célja: {destination}')
            else:
                reserved.add(key)
                jobs.append(ConversionJob(source, destination))
        except (OSError, ValueError) as exc:
            skip(source, str(exc))
    return jobs, skipped


def run_batch(jobs, szelesseg, magassag, minoseg, mod, background_color='white',
              preserve_dates=True, date_preserver=None, skipped=0,
              memory_limit_gb=DEFAULT_MEMORY_LIMIT_GB, max_workers=DEFAULT_WORKERS):
    if preserve_dates and date_preserver is None:
        with PhotoDatePreserver() as dates:
            result = run_batch(jobs, szelesseg, magassag, minoseg, mod,
                               background_color, preserve_dates, dates, skipped,
                               memory_limit_gb, max_workers)
            dates.summary()
            return result
    result = BatchResult(skipped=skipped)
    if not jobs:
        print(f'Konverzió: 0 sikeres, 0 hibás, {skipped} kihagyott.')
        return result
    cpu_count = os.cpu_count() or 1
    workers = min(len(jobs), max(1, max_workers), max(1, cpu_count // 2))
    # Egyetlen képhez marad az ImageMagick saját szálbeállítása.
    threads = 2 if workers > 1 else None
    print(f'Konvertálás: {len(jobs)} kép, legfeljebb {workers} párhuzamos feldolgozás, '
          f'képenként {memory_limit_gb:g} GB memórialimit.')
    started = time.perf_counter()
    iterator = iter(jobs)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {}

        def submit_next():
            job = next(iterator, None)
            if job is not None:
                future = executor.submit(_run_conversion, job, szelesseg, magassag,
                                         minoseg, mod, background_color, threads,
                                         memory_limit_gb)
                pending[future] = job

        # Csak korlátozott számú munka kerül a sorba, sok ezer képnél is.
        for _ in range(workers * 2):
            submit_next()
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                job = pending.pop(future)
                submit_next()  # A CPU a dátummásolás közben is dolgozhat.
                try:
                    error = future.result()
                except Exception as exc:
                    error = str(exc) or type(exc).__name__
                if error:
                    result.failed += 1
                    print(f'Hiba: {job.source}: {error}')
                else:
                    result.converted += 1
                    # Kizárólag a fő szál használja az egyetlen ExifTool-folyamatot.
                    if preserve_dates:
                        date_preserver.copy(job.source, job.destination)
                done = result.converted + result.failed
                print(f'[{done}/{len(jobs)}] {"Hibás" if error else "Kész"}: {job.source} -> {job.destination}')
    print(f'Konverzió: {result.converted} sikeres, {result.failed} hibás, '
          f'{result.skipped} kihagyott; {time.perf_counter() - started:.1f} másodperc.')
    return result


def process_directory(directory, global_prefix, global_suffix, szelesseg, magassag, minoseg, mod, formatum, output_base_dir, background_color="white", preserve_dates=True, date_preserver=None, memory_limit_gb=DEFAULT_MEMORY_LIMIT_GB, max_workers=DEFAULT_WORKERS):
    jobs, skipped = plan_conversions([directory], global_prefix, global_suffix, formatum, output_base_dir)
    return run_batch(jobs, szelesseg, magassag, minoseg, mod, background_color,
                     preserve_dates, date_preserver, skipped,
                     memory_limit_gb, max_workers)

def main():
    global auto_mode
    auto_mode = AUTO_ARG in sys.argv[1:]
    paths = [arg for arg in sys.argv[1:] if arg != AUTO_ARG]

    if not paths:
        # Kérdezzen meg egy mappát, ha nincs megadva parancssori argumentum
        directory = get_input("Adja meg a feldolgozandó mappát: ")
        if not directory or not os.path.isdir(directory):
            print("Érvénytelen mappa.")
            return
        paths.append(directory)


    # Echo arguments
    print("ARGS start")
    print(" ".join(paths))
    print("ARGS stop")

    # Set output base directory
    output_base_dir = get_input("\nAdja meg a cél mappát (vagy hagyja üresen): ")
    if output_base_dir:
        print(f"Kiválasztott cél mappa: {output_base_dir}")
    else:
        print("A konvertált fájlok a forrás melletti opt-webp-or-jpg almappába kerülnek.")

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
    while True:
        preserve_input = get_input("\nMobilos készítési idő megőrzése (EXIF + módosítás dátuma)? (i/n, default: i): ", default="i").strip().lower()
        if preserve_input in ("i", "n"):
            break
        print("Kérem, i vagy n értéket adjon meg.")
    preserve_dates = preserve_input == "i"
    if preserve_dates:
        print("A készítési időt a kimeneti EXIF-be másoljuk, és erre állítjuk a fájl módosítási idejét; a létrehozási időt nem állítjuk.")
    else:
        print("Külön dátummásolás nem történik; ez nem jelent metaadat-törlést.")

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

    # Képenkénti memórialimit: felső korlát, nem lefoglalás
    while True:
        memory_input = get_input(
            f"\nKépenkénti memórialimit GB-ban (default: {DEFAULT_MEMORY_LIMIT_GB:g}): ",
            default=str(DEFAULT_MEMORY_LIMIT_GB)).strip().replace(",", ".")
        try:
            memory_limit_gb = float(memory_input)
        except ValueError:
            memory_limit_gb = 0
        if memory_limit_gb > 0:
            break
        print("Kérem, pozitív számot adjon meg.")
    print(f"Kiválasztott memórialimit: {memory_limit_gb:g} GB képenként, "
          f"legfeljebb {DEFAULT_WORKERS} párhuzamos képpel.")

    jobs, skipped = plan_conversions(paths, global_prefix, global_suffix,
                                    formatum, output_base_dir)
    with PhotoDatePreserver(enabled=preserve_dates) as date_preserver:
        run_batch(jobs, szelesseg, magassag, minoseg, mod, background_color,
                  preserve_dates, date_preserver, skipped, memory_limit_gb)
        date_preserver.summary()

    # Pause before exit
    print("\nFeldolgozás vége: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not auto_mode:
        input("Nyomjon meg egy gombot a kilépéshez...")

if __name__ == "__main__":
    main()

