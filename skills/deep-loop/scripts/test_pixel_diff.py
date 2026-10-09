"""Runnable acceptance check for the pixel comparator; no extra test framework."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image


def main():
    script = Path(__file__).with_name('pixel_diff.py')
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        expected, actual = root / 'expected.png', root / 'actual.png'
        base = Image.new('RGBA', (4, 4), (255, 255, 255, 255))
        base.save(expected)
        base.save(actual)
        count = 0

        def run(code, status, *extra):
            nonlocal count
            count += 1
            out = root / f'run-{count}'
            proc = subprocess.run([sys.executable, str(script), '--expected', str(expected),
                                   '--actual', str(actual), '--output', str(out),
                                   '--max-diff-ratio', '0', *extra], capture_output=True, text=True)
            assert proc.returncode == code, (proc.returncode, proc.stdout, proc.stderr)
            result = json.loads((out / 'result.json').read_text())
            assert result['status'] == status, result
            return result, out

        result, out = run(0, 'PASS')
        assert result['comparison']['changedPixels'] == 0
        assert all((out / name).is_file() for name in ['expected.png', 'actual.png', 'diff.png'])
        changed = base.copy()
        changed.putpixel((0, 0), (250, 255, 255, 255))
        changed.save(actual)
        result, _ = run(1, 'FAIL')
        assert result['comparison']['changedPixels'] == 1
        assert result['comparison']['diffRatio'] == 1 / 16
        run(0, 'PASS', '--tolerance', '5')
        run(1, 'FAIL', '--tolerance', '4')
        run(0, 'PASS', '--max-diff-ratio', '0.0625')
        run(1, 'FAIL', '--max-diff-ratio', '0.0624')
        result, _ = run(1, 'FAIL', '--max-diff-ratio', '1', '--region', '0,0,1,1',
                        '--region-max-diff-ratio', '0')
        assert result['comparison']['passed'] and not result['regions'][0]['passed']
        run(0, 'PASS', '--max-diff-ratio', '1', '--region', '1,1,2,2',
            '--region-max-diff-ratio', '0')
        run(2, 'BLOCKED', '--region', '3,3,2,2', '--region-max-diff-ratio', '0')
        run(2, 'BLOCKED', '--region', '0,0,1,1')
        changed = base.copy()
        changed.putpixel((0, 0), (255, 255, 255, 0))
        changed.save(actual)
        run(1, 'FAIL')
        Image.new('RGBA', (3, 4)).save(actual)
        _, out = run(2, 'BLOCKED')
        assert not (out / 'diff.png').exists()
        actual.write_text('not an image')
        run(2, 'BLOCKED')
        actual.unlink()
        run(2, 'BLOCKED')
        base.save(actual)
        for value in ['nan', 'inf', '-1', '1.1']:
            proc = subprocess.run([sys.executable, str(script), '--expected', str(expected),
                                   '--actual', str(actual), '--output', str(root / 'invalid'),
                                   '--max-diff-ratio', value], capture_output=True)
            assert proc.returncode == 2 and not (root / 'invalid').exists()
        out = root / 'preserved'
        out.mkdir()
        marker = out / 'marker.txt'
        marker.write_text('keep')
        proc = subprocess.run([sys.executable, str(script), '--expected', str(expected),
                               '--actual', str(actual), '--output', str(out),
                               '--max-diff-ratio', '0'], capture_output=True)
        assert proc.returncode == 2 and marker.read_text() == 'keep'
        assert expected.read_bytes() == (root / 'run-1' / 'expected.png').read_bytes()
        print(f'{count} fixture comparisons plus input/output guards passed')


if __name__ == '__main__':
    main()
