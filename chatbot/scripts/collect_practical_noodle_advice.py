"""Snapshot and verify the selected dietitian advice before registering it."""
import hashlib
import json
from html.parser import HTMLParser

import httpx

from rag_app.config import ROOT


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def main():
    source_id = 'singhealth-noodle-choices'
    url = 'https://www.healthxchange.sg/how-to-prevent/food-tips/healthier-picks-at-the-food-court'
    collection = 'practical_meals_2026-10-31'
    folder = ROOT / 'data/collected' / collection
    folder.mkdir(parents=True, exist_ok=True)
    response = httpx.get(url, follow_redirects=True, timeout=45)
    response.raise_for_status()
    parser = PageText()
    parser.feed(response.text)
    text = ' '.join(' '.join(parser.parts).split())
    # Fail closed if the publisher changes the selected advice.
    excerpts = [
        'When having noodle dishes...',
        'Clear soup (e.g. yong tau foo, fish soup)',
        'Thickened soup, coconut based, oily soup (e.g. curry laksa, lor mee)',
        'Ask for less noodles and more vegetables.',
    ]
    for excerpt in excerpts:
        if excerpt not in text:
            raise ValueError('Publisher excerpt changed: ' + excerpt)
    raw_name = source_id + '.html'
    (folder / raw_name).write_bytes(response.content)
    original_digest = hashlib.sha256(response.content).hexdigest()
    segment = {
        'section': 'When having noodle dishes — eating out choices',
        'text': 'When having noodle dishes, choose:\n'
                'Clear soup (e.g. yong tau foo, fish soup) instead of thickened soup, coconut based, oily soup (e.g. curry laksa, lor mee).\n'
                'Ask for less noodles and more vegetables.',
        'locators': ['When having noodle dishes...', 'Choose / Instead of table'],
        'pages': [],
        'related_sections': ['endocrine-diet::4) Chọn chất đạm “nạc” và cách chế biến'],
    }
    curated = {
        'schema_version': 1, 'source_id': source_id,
        'original_url': url, 'original_sha256': original_digest,
        'segments': [segment],
    }
    filename = 'supplement-singhealth-noodle-choices.json'
    path = ROOT / 'data' / filename
    path.write_text(json.dumps(curated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    entry = {
        'id': source_id, 'filename': filename, 'format': 'curated',
        'title': 'SingHealth / KKH dietitians — Healthier Picks at the Food Court',
        'url': url, 'year': 2026,
        'version': 'Selected noodle advice collected 31/10/2026; collection year, not publication year.',
        'enabled': True, 'role': 'knowledge', 'language': 'en',
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'collection_release': '2026-10-31',
        'segments': [{'section': segment['section']}],
        'warnings': ['Hướng dẫn chọn món nói chung, không xác định khẩu phần cá nhân cho người bệnh đái tháo đường.'],
        'original_collection': collection, 'original_raw_file': raw_name,
        'original_sha256': original_digest,
    }
    manifest_path = ROOT / 'config/sources.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['sources'] = [s for s in manifest['sources'] if s['id'] != source_id] + [entry]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Verified and registered:', source_id)


if __name__ == '__main__':
    main()
