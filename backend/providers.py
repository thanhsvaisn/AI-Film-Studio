"""Local-only provider contract. Never downloads weights or falls back to a paid API."""
from typing import Protocol
from pathlib import Path
import importlib.util
import os


class TTSProvider(Protocol):
    def synthesize(self, text: str, output: Path, reference: Path): ...


def readiness():
    model = os.environ.get('VOXCPM_MODEL_DIR', '')
    return dict(id='voxcpm2_local', installed=importlib.util.find_spec('voxcpm') is not None,
                model_ready=bool(model and (Path(model) / 'model.safetensors').is_file()
                                 and (Path(model) / 'model.safetensors').stat().st_size > 4_500_000_000
                                 and (Path(model) / 'audiovae.pth').is_file()
                                 and (Path(model) / 'config.json').is_file()), paid_api=False)


class VoxCPMProvider:
    def __init__(self):
        ready = readiness()
        if not ready['installed'] or not ready['model_ready']:
            raise ValueError('Chưa sẵn sàng: cài VoxCPM và đặt VOXCPM_MODEL_DIR tới mô hình đã tải.')
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from voxcpm import VoxCPM
        self.model = VoxCPM.from_pretrained(os.environ['VOXCPM_MODEL_DIR'], load_denoiser=False)

    def synthesize(self, text, output, reference=None):
        import soundfile as sf
        options = dict(text=text, cfg_value=2.0, inference_timesteps=10)
        if reference is not None:
            options['reference_wav_path'] = str(reference)
        wav = self.model.generate(**options)
        sf.write(str(output), wav, self.model.tts_model.sample_rate)
