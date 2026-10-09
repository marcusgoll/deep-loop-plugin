"""Compare matched image captures; exits 0 PASS, 1 FAIL, 2 BLOCKED."""
import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys

try:
    from PIL import Image, ImageChops, __version__ as pillow_version
except ImportError:
    print(json.dumps({'status': 'BLOCKED', 'diagnostic': 'Python Pillow is required'}), file=sys.stderr)
    sys.exit(2)


def ratio(value):
    try:
        number = float(value)
        if not math.isfinite(number) or not 0 <= number <= 1:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError('ratio must be finite and between 0 and 1')


def region(value):
    try:
        x, y, width, height = map(int, value.split(','))
        if min(x, y) < 0 or min(width, height) <= 0:
            raise ValueError
        return x, y, x + width, y + height
    except ValueError:
        raise argparse.ArgumentTypeError('region must be X,Y,WIDTH,HEIGHT with positive size')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(mask, limit):
    changed = mask.histogram()[255]
    total = mask.width * mask.height
    fraction = changed / total
    return {'changedPixels': changed, 'totalPixels': total, 'diffRatio': fraction,
            'maxDiffRatio': limit, 'passed': fraction <= limit}


def compare_images(expected, actual, tolerance, max_diff_ratio, regions, region_max_diff_ratio):
    """Inspect existing pixels in memory; no argv, files, capture or generated artifacts."""
    expected, actual = expected.convert('RGBA'), actual.convert('RGBA')
    if expected.size != actual.size:
        raise ValueError('Pixel dimensions differ; recapture or document normalization first')
    if regions and region_max_diff_ratio is None:
        raise ValueError('Regions require --region-max-diff-ratio')
    for box in regions:
        if box[2] > expected.width or box[3] > expected.height:
            raise ValueError(f'Region outside image: {box}')
    channels = ImageChops.difference(expected, actual).split()
    maximum = channels[0]
    for channel in channels[1:]:
        maximum = ImageChops.lighter(maximum, channel)
    mask = maximum.point([255 if value > tolerance else 0 for value in range(256)])
    comparison = measure(mask, max_diff_ratio)
    measures = [{'box': list(box), **measure(mask.crop(box), region_max_diff_ratio)} for box in regions]
    return mask, comparison, measures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--actual', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tolerance', type=int, choices=range(256), default=0, metavar='0..255')
    parser.add_argument('--max-diff-ratio', type=ratio, required=True)
    parser.add_argument('--region', type=region, action='append', default=[])
    parser.add_argument('--region-max-diff-ratio', type=ratio)
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(json.dumps({'status': 'BLOCKED', 'diagnostic': str(error)}), file=sys.stderr)
        return 2

    result = {'status': 'BLOCKED', 'diagnostic': '', 'inputs': {}, 'artifacts': {},
              'verifierSha256': digest(Path(__file__)),
              'runtime': {'python': sys.version.split()[0], 'pillow': pillow_version},
              'tolerance': args.tolerance, 'maxDiffRatio': args.max_diff_ratio,
              'regionMaxDiffRatio': args.region_max_diff_ratio}

    def save(image, name):
        path = args.output / f'{name}.png'
        image.save(path)
        result['artifacts'][name] = {'path': str(path.resolve()), 'sha256': digest(path)}

    try:
        images = []
        for name, path in [('expected', args.expected), ('actual', args.actual)]:
            data = path.read_bytes()
            result['inputs'][name] = {'path': str(path.resolve()), 'sha256': hashlib.sha256(data).hexdigest()}
            with Image.open(BytesIO(data)) as source:
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Use single-frame captures')
                image = source.convert('RGBA')
            images.append(image)
            result['inputs'][name]['size'] = list(image.size)
            save(image, name)
        expected, actual = images
        mask, result['comparison'], result['regions'] = compare_images(
            expected, actual, args.tolerance, args.max_diff_ratio, args.region, args.region_max_diff_ratio)
        passed = result['comparison']['passed'] and all(item['passed'] for item in result['regions'])
        context = Image.blend(actual.convert('RGB'), Image.new('RGB', actual.size, 'white'), 0.65)
        save(Image.composite(Image.new('RGB', actual.size, 'magenta'), context, mask), 'diff')
        result['status'] = 'PASS' if passed else 'FAIL'
        result['diagnostic'] = 'All declared pixel limits met' if passed else 'Pixel limit exceeded'
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        result['status'] = 'BLOCKED'
        result['diagnostic'] = str(error)
    try:
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except OSError as error:
        print(json.dumps({'status': 'BLOCKED', 'diagnostic': str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[result['status']]


if __name__ == '__main__':
    sys.exit(main())
