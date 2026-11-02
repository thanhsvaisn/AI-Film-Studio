"""Manual smoke test: create short local samples without downloading models."""

from pathlib import Path

from backend import media, store
from backend.locales import default_sample
from backend.providers import VoxCPMProvider


def main():
    output = store.ROOT / 'voice_smoke'
    output.mkdir(exist_ok=True)
    provider = VoxCPMProvider()
    for locale in ('th-TH', 'id-ID', 'hi-IN', 'ja-JP'):
        path = output / f'{locale}.wav'
        provider.synthesize(default_sample(locale), path)
        duration, streams = media.probe(path)
        if not any(s['codec_type'] == 'audio' for s in streams):
            raise RuntimeError(f'Không có âm thanh: {locale}')
        print(f'{locale}: {duration:.2f} s → {path}', flush=True)


if __name__ == '__main__':
    main()
