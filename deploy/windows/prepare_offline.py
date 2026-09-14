"""Download a pinned official Windows installer/wheel bundle; never execute it."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.parse
import urllib.request


def prepare(output, manifest_path=None):
    manifest_path = manifest_path or Path(__file__).with_name('offline-runtime.json')
    manifest = json.loads(Path(manifest_path).read_text())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for artifact in manifest['files']:
        relative = Path(artifact['file'])
        target = (output / relative).resolve()
        if relative.is_absolute() or output not in target.parents:
            raise ValueError('Artifact path escapes bundle')
        url = urllib.parse.urlsplit(artifact['url'])
        if url.scheme != 'https' or url.hostname not in ('www.python.org', 'files.pythonhosted.org') or url.username or url.query or url.fragment:
            raise ValueError('Unexpected artifact origin')
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == artifact['sha256']:
            continue
        with urllib.request.urlopen(artifact['url'], timeout=60) as response:
            if urllib.parse.urlsplit(response.url).hostname != url.hostname:
                raise ValueError('Unexpected artifact redirect')
            data = response.read()
        if hashlib.sha256(data).hexdigest() != artifact['sha256']:
            raise ValueError('Artifact checksum mismatch')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.download')
        temporary.write_bytes(data)
        temporary.replace(target)
    return len(manifest['files'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(f'{prepare(args.output)} official artifacts verified; nothing installed or activated.')
