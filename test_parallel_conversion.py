"""Kötegelt tervezés, párhuzamosság és a korábbi képi eredmény ellenőrzése."""

import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import KepKonvForFilesOrDirs as converter


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='parallel-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.log)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def source(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
        return path

    def plan(self, paths, output=None):
        return converter.plan_conversions([str(p) for p in paths], '', '', 'jpg',
                                           str(output or self.root / 'out'))

    def test_duplicate_inputs_and_cross_directory_collisions(self):
        first = self.source('a/same.jpg')
        second = self.source('b/same.jpeg')
        jobs, skipped = self.plan([first, first.parent, second])
        self.assertEqual(skipped, 2)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, str(first))

    def test_png_suffix_collision_is_detected_before_launch(self):
        png = self.source('a/image.png')
        jpg = self.source('b/image.png.jpg')
        jobs, skipped = self.plan([png, jpg])
        self.assertEqual(skipped, 1)
        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].destination.endswith('image.png.jpg'))

    def test_existing_destination_and_source_are_never_overwritten(self):
        src = self.source('a.jpg')
        existing = self.source('out/a.jpg')
        jobs, skipped = self.plan([src])
        self.assertEqual((jobs, skipped), ([], 1))
        self.assertEqual(existing.read_bytes(), b'fixture')
        jobs, skipped = self.plan([src], self.root)
        self.assertEqual((jobs, skipped), ([], 1))

    def test_directory_named_jpg_and_unsupported_explicit_paths_are_skipped(self):
        (self.root / 'fake.jpg').mkdir()
        self.source('valid.jpg')
        unsupported = self.source('unsupported.webp')
        jobs, skipped = self.plan([self.root, unsupported, self.root / 'missing.jpg'])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(skipped, 3)

    def test_global_and_local_names_and_non_recursive_selection(self):
        src = self.source('photos/pic.jpg')
        self.source('photos/nested/hidden.jpg')
        (src.parent / 'suffix.txt').write_text('local', encoding='ascii')
        jobs, skipped = converter.plan_conversions([str(src.parent)], 'global-', '', 'webp', '')
        self.assertEqual(skipped, 0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].destination, str(src.parent / 'opt-webp-or-jpg/global-pic-local.webp'))

    def test_six_converters_overlap_but_dates_run_on_main_thread(self):
        jobs = [converter.ConversionJob(f'source-{i}.jpg', f'output-{i}.webp') for i in range(12)]
        barrier = threading.Barrier(6, timeout=5)
        worker_ids = set()
        lock = threading.Lock()
        main_thread = threading.get_ident()
        dates = Mock()
        copied = []

        def render(job, *args):
            with lock:
                worker_ids.add(threading.get_ident())
            barrier.wait()
            if job == jobs[1]:
                return 'hibás kép'
            if job == jobs[4]:
                raise OSError('olvasási hiba')
            return ''

        def copy(source, dest):
            self.assertEqual(threading.get_ident(), main_thread)
            copied.append((source, dest))

        dates.copy.side_effect = copy
        with patch.object(converter.os, 'cpu_count', return_value=12), \
                patch.object(converter, '_run_conversion', side_effect=render):
            result = converter.run_batch(jobs, 30, 30, 75, 'n', date_preserver=dates, skipped=2)
        self.assertEqual(len(worker_ids), 6)
        self.assertEqual(result, converter.BatchResult(10, 2, 2))
        expected = {(j.source, j.destination) for i, j in enumerate(jobs) if i not in (1, 4)}
        self.assertEqual(set(copied), expected)

    def test_failed_render_leaves_no_partial_target(self):
        src = self.source('bad.jpg')
        dest = self.root / 'out/failed.webp'

        def fail(command, **kwargs):
            Path(command[-1]).write_bytes(b'incomplete')
            return subprocess.CompletedProcess(command, 1, '', 'invalid image')

        with patch.object(converter.subprocess, 'run', side_effect=fail):
            error = converter._run_conversion(converter.ConversionJob(str(src), str(dest)),
                                               30, 30, 75, 'n', 'white', 2)
        self.assertIn('invalid image', error)
        self.assertFalse(dest.exists())
        self.assertEqual(list(dest.parent.iterdir()), [])

    def test_large_batch_has_bounded_queue_and_no_date_tool_when_disabled(self):
        jobs = [converter.ConversionJob(f'{i}.jpg', f'{i}.webp') for i in range(1000)]
        original_wait = converter.wait
        queue_sizes = []

        def bounded_wait(pending, **kwargs):
            queue_sizes.append(len(pending))
            # A sor legfeljebb a párhuzamos feldolgozások kétszerese.
            self.assertLessEqual(len(pending), converter.DEFAULT_WORKERS * 2)
            return original_wait(pending, **kwargs)

        with patch.object(converter.os, 'cpu_count', return_value=12), \
                patch.object(converter, '_run_conversion', return_value=''), \
                patch.object(converter, 'wait', side_effect=bounded_wait), \
                patch.object(converter, 'PhotoDatePreserver') as dates:
            result = converter.run_batch(jobs, 30, 30, 75, 'n', preserve_dates=False)
        self.assertEqual(result.converted, 1000)
        self.assertTrue(queue_sizes)
        dates.assert_not_called()

    def test_target_created_during_render_is_not_overwritten(self):
        src = self.source('source.jpg')
        dest = self.root / 'out/race.webp'

        def render(command, **kwargs):
            Path(command[-1]).write_bytes(b'new conversion')
            dest.write_bytes(b'another process created this')
            return subprocess.CompletedProcess(command, 0, '', '')

        with patch.object(converter.subprocess, 'run', side_effect=render):
            error = converter._run_conversion(converter.ConversionJob(str(src), str(dest)),
                                               30, 30, 75, 'n', 'white', 2)
        self.assertTrue(error)
        self.assertEqual(dest.read_bytes(), b'another process created this')
        self.assertEqual(list(dest.parent.iterdir()), [dest])

    def test_missing_magick_is_a_reported_failure(self):
        src = self.source('source.jpg')
        dest = self.root / 'out/missing.webp'
        jobs = [converter.ConversionJob(str(src), str(dest))]
        with patch.object(converter.subprocess, 'run', side_effect=FileNotFoundError('magick')):
            result = converter.run_batch(jobs, 30, 30, 75, 'n', preserve_dates=False)
        self.assertEqual(result.failed, 1)
        self.assertFalse(dest.exists())
        self.assertEqual(list(dest.parent.iterdir()), [])

    @unittest.skipUnless(shutil.which('magick'), 'ImageMagick szükséges')
    def test_parallel_pixels_match_original_commands_in_every_mode_and_format(self):
        jpg = self.root / 'original.jpg'
        png = self.root / 'transparent.png'

        def run(*args):
            return subprocess.run(args, check=True, capture_output=True).stdout

        run('magick', '-size', '120x80', 'gradient:red-blue', '-quality', '95', str(jpg))
        run('magick', '-size', '120x80', 'xc:none', '-fill', 'red', '-draw',
            'circle 60,40 85,40', str(png))
        for mode in ('n', 'c', 't'):
            for fmt in ('jpg', 'webp', 'avif'):
                with self.subTest(mode=mode, format=fmt):
                    out = self.root / f'{mode}-{fmt}'
                    jobs, skipped = converter.plan_conversions([str(jpg), str(png)], '', '', fmt, str(out))
                    result = converter.run_batch(jobs, 60, 60, 75, mode, 'black', preserve_dates=False)
                    self.assertEqual(result, converter.BatchResult(2, 0, 0))
                    for job in jobs:
                        reference = self.root / f'reference-{Path(job.source).suffix[1:]}.{fmt}'
                        command = ['magick', job.source, '-auto-orient']
                        if mode == 'n':
                            command += ['-thumbnail', '60x60>', '-quality', '75']
                            if fmt == 'avif':
                                command += ['-define', 'heic:compression=av1', '-define',
                                            'heic:speed=6', '-define', 'heic:quality=75']
                        elif mode == 'c':
                            command += ['-resize', '60x60^', '-quality', '75', '-gravity',
                                        'center', '-extent', '60x60']
                        else:
                            command += ['-resize', '60x60', '-background', 'black', '-gravity',
                                        'center', '-extent', '60x60', '-quality', '75']
                        run(*command, str(reference))
                        def signature(path):
                            return run('magick', str(path), '-format', '%wx%h %[signature]', 'info:')
                        self.assertEqual(signature(reference), signature(job.destination))
                    self.assertFalse(list(out.glob('.kepkonv-*')))


if __name__ == '__main__':
    unittest.main()
