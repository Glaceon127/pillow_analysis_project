"""Run CVE collection and save to data/processed/pillow_cves.json

This script calls CVECollector.collect() and prints summary.
"""
import os
import sys

# Ensure project root is on sys.path so `src` package can be imported when script
# is executed from tools/ or elsewhere.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data_pipeline.cve_collector import CVECollector
try:
    import requests  # quick check for required third-party dependency
except Exception:
    print('Missing required package "requests".')
    print('Install dependencies with:')
    print('  python -m pip install -r "{}"'.format(os.path.abspath(os.path.join(PROJECT_ROOT, 'requirements.txt'))))
    sys.exit(1)

if __name__ == '__main__':
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    out_path = os.path.join(base, 'data', 'processed', 'pillow_cves.json')
    collector = CVECollector()
    items = collector.collect(keyword='Pillow', save_path=out_path, verbose=True)
    print(f'Collected {len(items)} CVE items and saved to: {out_path}')
    if items:
        print('Example item:')
        print(items[0])
