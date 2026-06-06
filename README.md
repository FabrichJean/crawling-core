# crawling-core

Noyau commun pour batir des pipelines de scraping par plateforme (creators,
videos courtes/longues, forums, ...). Chaque plateforme reste un projet
independant avec sa propre strategie reseau/chiffrement et sa config; ce
package fournit la logique qui ne change pas d'une plateforme a l'autre.

## Ce que le noyau fournit

- `crawling_core.models` — `Creator`, `Media`, `ForumPost`: dataclasses
  normalisees construites via `from_raw(data, mapping=...)`, qui gardent
  toujours le payload original dans `.raw`. Le `mapping` permet d'indiquer
  quelles cles API correspondent a quel champ normalise sans sous-classer.
- `crawling_core.codec` — `Codec` Protocol + `NoopCodec` (JSON brut) +
  `AesCfbCodec` (enveloppe AES-CFB signee, schema courant des sites PWA).
  Si l'enveloppe d'un site differe, ecris ton propre `Codec`.
- `crawling_core.adapters.base` — Protocols `PlatformAdapter`,
  `CreatorListing`, `CreatorMediaListing`, `ForumListing`: le contrat que
  chaque plateforme implemente. Implemente seulement ce dont ta strategie a
  besoin.
- `crawling_core.pipeline` — boucles d'orchestration generiques
  (`run_main_listing`, `run_creator_media`, `run_paginated`) qui paginent et
  delèguent a des callbacks; aucune connaissance specifique a un site.
- `crawling_core.storage` — `SqliteStorage`: stockage generique
  creators/media/forum_posts avec colonnes normalisees + `raw_json` +
  `extra_json` (bag libre pour le statut pipeline: `downloaded`,
  `transcoded`, `local_path`, `cdn_url`, ...). Pas de migration a chaque
  nouvelle plateforme.
- `crawling_core.download` — `M3U8Downloader`: telechargement + reecriture
  de playlist, agnostique du shape de config (recoit dir/headers/timeout).
- `crawling_core.transcode` — `FfmpegTranscoder`: transcodage M3U8 -> MP4
  sur pool de threads.
- `crawling_core.output` — `LocalOutput`: depot local du fichier final +
  export JSON (media + creator), equivalent generique de l'ancien
  `VmsSender`.
- `crawling_core.config` — helpers `.env` (`load_env_file`, `env`,
  `env_int`, `env_bool`, `ensure_dirs`) pour batir un `Settings` par
  plateforme sans dupliquer le parsing.

## Ce qui reste dans chaque projet-plateforme

- L'**adapter** concret (implémente `PlatformAdapter` + les Protocols
  optionnels pertinents): construction des requetes, pagination, mapping
  JSON -> `Creator`/`Media`/`ForumPost`, et le `Codec` si besoin.
- Le **`Settings`** specifique (cles API, hote, prefixes CDN, ...), construit
  avec les helpers de `crawling_core.config`.
- Tout ce qui est specifique a la destination finale (upload R2/VMS/CDN,
  signature OAuth, etc.).

## Exemple d'integration minimale

```python
from pathlib import Path

from crawling_core import (
    Creator, Media, NoopCodec, M3U8Downloader, FfmpegTranscoder,
    LocalOutput, SqliteStorage,
)
from crawling_core.pipeline import run_main_listing


class MyPlatformAdapter:
    def __init__(self, settings):
        self.settings = settings
        self.codec = NoopCodec()  # ou AesCfbCodec(key=..., iv=...)

    def get_total_pages(self) -> int:
        ...  # appelle l'API liste, retourne le nombre de pages

    def fetch_page(self, page: int) -> list[Media]:
        data = ...  # requete + self.codec.decode_response(...)
        return [Media.from_raw(item, kind="long") for item in data["items"]]

    def build_media_url(self, media: Media) -> str:
        return media.play_url


storage = SqliteStorage(Path("platform.db"))
storage.initialize()

adapter = MyPlatformAdapter(settings)
downloader = M3U8Downloader(output_dir=Path("m3u8"), build_url=adapter.build_media_url, storage=storage)
transcoder = FfmpegTranscoder(output_dir=Path("mp4"), build_url=adapter.build_media_url, storage=storage)
output = LocalOutput(final_dir=Path("vms"), export_dir=Path("exports"), storage=storage)

def handle(media: Media) -> None:
    storage.upsert_media(media)
    result = downloader.download(media)
    if result:
        path = transcoder.transcode(media)
        if path:
            output.deliver(media, path)

run_main_listing(adapter, handle, max_pages=2)
```

## Installation dans un projet-plateforme

En mode editable, depuis le repo de la plateforme:

```bash
python -m pip install -e ../crawling-core
```

ou en dependance de chemin dans `pyproject.toml`:

```toml
dependencies = [
    "crawling-core @ file:///absolute/path/to/crawling-core",
]
```

Pour le `Codec` AES, installe l'extra crypto: `pip install -e "../crawling-core[crypto]"`.
