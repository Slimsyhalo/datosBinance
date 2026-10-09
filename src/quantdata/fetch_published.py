"""Gather the published joint dataset and raw trades, validating asset hashes."""
import argparse
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from .acquire import sha256


def safe_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', value) or value in {'.', '..'}:
        raise ValueError('Unsafe release tag or asset name')
    return value


def extract_verified(archive_path, asset, destination, trades_only=False):
    if archive_path.stat().st_size != asset['bytes'] or sha256(archive_path) != asset['sha256']:
        raise ValueError('Asset size or SHA256 mismatch: ' + asset['asset'])
    destination = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        actual = {r.filename for r in archive.infolist() if not r.is_dir()}
        if actual != set(asset['members']):
            raise ValueError('ZIP members differ from published catalog')
        selected = []
        for member in sorted(actual):
            path = PurePosixPath(member)
            if path.is_absolute() or '..' in path.parts or '\\' in member:
                raise ValueError('Unsafe ZIP member')
            target = (destination / member).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('ZIP member escapes destination')
            if trades_only and not (member.startswith('data/raw/') and '/trades/' in member):
                continue
            if not member.startswith('data/'):
                raise ValueError('Unexpected non-data member')
            selected.append((member, target))
        for member, target in selected:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open('wb') as out:
                shutil.copyfileobj(source, out)


def download(repo, tag, name, folder):
    safe_name(tag)
    safe_name(name)
    subprocess.run(['gh', 'release', 'download', tag, '--repo', repo,
                    '--pattern', name, '--dir', str(folder), '--clobber'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='Slimsyhalo/datosBinance')
    parser.add_argument('--tag', required=True, help='Tag of the published joint release')
    parser.add_argument('--output', default='downloaded-dataset')
    args = parser.parse_args()
    safe_name(args.tag)
    root = Path(args.output).resolve()
    cache = root / 'release-cache'
    meta = root / 'reports'
    meta.mkdir(parents=True, exist_ok=True)
    for name in ['ASSETS.json', 'JOINT_DELIVERY.json', 'JOINT_DELIVERY.md', 'QUALITY.json',
                 'TRADES_FULL.json', 'ACQUISITION.json', 'MACRO.json', 'FUNDING_API.json', 'MISSING.json']:
        download(args.repo, args.tag, name, meta)
    summary = json.loads((meta/'JOINT_DELIVERY.json').read_text())
    tasks = [(args.tag, r, False) for r in json.loads((meta/'ASSETS.json').read_text())]
    tasks += [(r['tag'], r, True) for r in summary['campaign_data_assets']
              if any(m.startswith('data/raw/') and '/trades/' in m for m in r['members'])]
    for index, (tag, asset, trades_only) in enumerate(tasks, 1):
        folder = cache / safe_name(tag)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe_name(asset['asset'])
        valid = target.exists() and target.stat().st_size == asset['bytes'] and sha256(target) == asset['sha256']
        if not valid:
            download(args.repo, tag, asset['asset'], folder)
        extract_verified(target, asset, root, trades_only=trades_only)
        print(json.dumps({'verified_assets': index, 'total_assets': len(tasks), 'asset': asset['asset']}), flush=True)
    print(json.dumps({'dataset_directory': str(root), 'source_files_missing': summary['remaining_source_files'],
                      'all_requested_categories_complete': summary['all_requested_categories_complete']}))


if __name__ == '__main__':
    main()
