"""Valódi ImageMagick/ExifTool integrációs ellenőrzések ideiglenes képekkel.

Futtatás: python -m unittest -v test_photo_dates
"""

import contextlib
import io
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import KepKonvForFilesOrDirs as converter
from photo_dates import ExifToolSession, PhotoDatePreserver


EXIFTOOL = Path(__file__).resolve().with_name('exiftool.exe')


@unittest.skipUnless(EXIFTOOL.is_file() and shutil.which('magick'), 'ImageMagick és ExifTool szükséges')
class PhotoDateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='photo-date-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        self.src = self.root / 'árvíztűrő mobil kép.jpg'
        self.run_tool('magick', '-size', '40x20', 'xc:red', str(self.src))
        self.run_tool(str(EXIFTOOL), '-overwrite_original',
                      '-DateTimeOriginal=2024:06:15 14:37:42',
                      '-OffsetTimeOriginal=+02:00', '-SubSecTimeOriginal=123',
                      '-Orientation#=6', str(self.src))
        # A másolás dátuma szándékosan eltér a fényképezés időpontjától.
        os.utime(self.src, (1700000000, 1700000000))

    @staticmethod
    def run_tool(*args):
        return subprocess.run(args, check=True, capture_output=True).stdout

    def read_tags(self, path):
        return json.loads(self.run_tool(str(EXIFTOOL), '-j', '-n',
                          '-DateTimeOriginal', '-OffsetTimeOriginal',
                          '-SubSecTimeOriginal', '-Orientation', str(path)))[0]

    def test_all_modes_formats_and_png_source_share_one_process(self):
        png = self.root / 'mobil.png'
        self.run_tool('magick', str(self.src), str(png))
        self.run_tool(str(EXIFTOOL), '-overwrite_original', '-TagsFromFile',
                      str(self.src), '-all:all', str(png))
        expected = datetime.fromisoformat('2024-06-15T14:37:42.123+02:00').timestamp()
        with PhotoDatePreserver() as dates:
            process = None
            for src in (self.src, png):
                for mode in ('n', 'c', 't'):
                    for fmt in ('jpg', 'webp', 'avif'):
                        with self.subTest(source=src.suffix, mode=mode, fmt=fmt):
                            dest = self.root / f'{src.suffix[1:]}-{mode}.{fmt}'
                            self.assertTrue(converter.convert_image(
                                str(src), str(dest), 30, 30, 75, mode, '', date_preserver=dates))
                            if src.suffix == '.png':
                                dest = dest.with_suffix(f'.png.{fmt}')
                            tags = self.read_tags(dest)
                            self.assertEqual(tags['DateTimeOriginal'], '2024:06:15 14:37:42')
                            self.assertEqual(tags['OffsetTimeOriginal'], '+02:00')
                            self.assertEqual(str(tags['SubSecTimeOriginal']), '123')
                            self.assertIn(tags.get('Orientation'), (None, 1))
                            self.assertAlmostEqual(dest.stat().st_mtime, expected, places=4)
                            if process is None:
                                process = dates.session.process
                            self.assertIs(process, dates.session.process)
            self.assertEqual(dates.copied, 18)
            self.assertEqual(dates.failed, 0)
        self.assertIsNotNone(process.poll())

    def test_no_date_does_not_invent_one(self):
        self.run_tool(str(EXIFTOOL), '-overwrite_original', '-all=', str(self.src))
        dest = self.root / 'missing.jpg'
        with PhotoDatePreserver() as dates:
            converter.convert_image(str(self.src), str(dest), 30, 30, 75, 'n', '', date_preserver=dates)
            self.assertEqual(dates.missing, 1)
            self.assertEqual(dates.failed, 0)
        self.assertNotIn('DateTimeOriginal', self.read_tags(dest))
        self.assertNotEqual(round(dest.stat().st_mtime), 1700000000)

    def test_no_timezone_uses_local_time_and_keeps_exif(self):
        self.run_tool(str(EXIFTOOL), '-overwrite_original', '-OffsetTimeOriginal=', str(self.src))
        dest = self.root / 'local.webp'
        with PhotoDatePreserver() as dates:
            converter.convert_image(str(self.src), str(dest), 30, 30, 75, 'n', '', date_preserver=dates)
            self.assertEqual(dates.local_timezone, 1)
        expected = datetime(2024, 6, 15, 14, 37, 42, 123000).timestamp()
        self.assertAlmostEqual(dest.stat().st_mtime, expected, places=4)
        self.assertNotIn('OffsetTimeOriginal', self.read_tags(dest))

    def test_disabled_does_not_start_exiftool(self):
        with PhotoDatePreserver(enabled=False) as dates:
            for mode in ('n', 'c', 't'):
                converter.convert_image(str(self.src), str(self.root / f'off-{mode}.jpg'),
                                        30, 30, 75, mode, '', preserve_dates=False,
                                        date_preserver=dates)
            self.assertIsNone(dates.session.process)
            self.assertEqual(dates.copied, 0)

    def test_failed_conversion_never_changes_existing_dates(self):
        dest = self.root / 'old.webp'
        self.run_tool('magick', str(self.src), str(dest))
        os.utime(dest, (1700000000, 1700000000))
        with PhotoDatePreserver() as dates, patch.object(
                converter.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertFalse(converter.convert_image(str(self.src), str(dest),
                             30, 30, 75, 'n', '', date_preserver=dates))
            self.assertIsNone(dates.session.process)
        self.assertEqual(dest.stat().st_mtime, 1700000000)

    def test_source_cannot_be_overwritten(self):
        original = self.src.read_bytes()
        self.assertFalse(converter.convert_image(str(self.src), str(self.src), 10, 10, 75, 'n', ''))
        self.assertEqual(original, self.src.read_bytes())

    def test_missing_tool_is_reported_without_repeated_start_attempts(self):
        with PhotoDatePreserver(executable=str(self.root / 'missing.exe')) as dates:
            self.assertFalse(dates.copy(str(self.src), str(self.root / 'out.jpg')))
            failure = dates.session.failure
            self.assertFalse(dates.copy(str(self.src), str(self.root / 'out.jpg')))
            self.assertEqual(dates.session.failure, failure)
            self.assertEqual(dates.failed, 2)

    def test_failed_command_does_not_break_next_command(self):
        session = ExifToolSession()
        self.addCleanup(session.close)
        with self.assertRaises(RuntimeError):
            session.execute(['-j', str(self.root / 'missing.jpg')])
        output, _ = session.execute(['-j', '-DateTimeOriginal', str(self.src)])
        self.assertEqual(json.loads(output)[0]['DateTimeOriginal'], '2024:06:15 14:37:42')

    def test_timeout_stops_process(self):
        session = ExifToolSession()
        self.addCleanup(session.close)
        session.execute(['-ver'])
        process = session.process
        session.timeout = 0.05
        # Elveszett válasz szimulálása: a vezérlő ne várjon korlátlanul.
        with patch.object(session, 'stdout', queue.Queue()), self.assertRaises(RuntimeError):
            session.execute(['-ver'])
        self.assertIsNotNone(process.poll())
        self.assertIsNone(session.process)

    def test_invalid_date_never_writes_destination(self):
        with PhotoDatePreserver() as dates, patch.object(dates.session, 'execute',
                return_value=('[{"DateTimeOriginal":"0000:00:00 00:00:00"}]', '')) as execute:
            self.assertFalse(dates.copy(str(self.src), str(self.root / 'out.jpg')))
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(dates.failed, 1)

    def test_forced_shutdown_closes_reader_threads(self):
        session = ExifToolSession()
        self.addCleanup(session.close)
        session.execute(['-ver'])
        process = session.process
        real_wait = process.wait
        calls = 0

        def stalled_wait(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise subprocess.TimeoutExpired('exiftool', 5)
            return real_wait(*args, **kwargs)

        # A szabályos leállítás üzenetét elnyeljük: a teljes folyamatfát kell leállítani.
        with patch.object(process.stdin, 'write'), patch.object(process, 'wait', stalled_wait):
            session.close()
        self.assertIsNotNone(process.poll())
        self.assertTrue(all(not reader.is_alive() for reader in session.readers))

    def test_main_shares_session_between_file_and_directory_and_closes_it(self):
        folder = self.root / 'folder'
        folder.mkdir()
        expected = {self.src.stem: '2024:06:15 14:37:42',
                    'a': '2024:06:15 14:38:42', 'b': '2024:06:15 14:39:42'}
        for name in ('a.jpg', 'b.jpg'):
            shutil.copyfile(self.src, folder / name)
            self.run_tool(str(EXIFTOOL), '-overwrite_original',
                          '-DateTimeOriginal=' + expected[Path(name).stem], str(folder / name))
        dates = PhotoDatePreserver()
        # Utolso ket ures valasz: memorialimit (default) es a kilepeshez varo input.
        answers = [str(self.root / 'out'), '', '', '30', '30', '75', ' I ', 'n', 'w', '', '']
        with patch('sys.argv', ['converter', str(self.src), str(folder)]), \
                patch('builtins.input', side_effect=answers), \
                patch.object(converter, 'PhotoDatePreserver', return_value=dates):
            converter.main()
        self.assertEqual(dates.copied, 3)
        self.assertEqual(dates.failed, 0)
        self.assertEqual(dates.session.sequence, 6)
        self.assertIsNone(dates.session.process)
        for stem, taken in expected.items():
            output = self.root / 'out' / f'{stem}.webp'
            self.assertEqual(self.read_tags(output)['DateTimeOriginal'], taken)
            timestamp = datetime.strptime(taken + '+0200', '%Y:%m:%d %H:%M:%S%z').timestamp()
            self.assertAlmostEqual(output.stat().st_mtime, timestamp + 0.123, places=4)


if __name__ == '__main__':
    unittest.main()
