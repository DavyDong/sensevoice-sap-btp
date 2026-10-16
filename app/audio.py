import io
import math

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def decode_audio(payload: bytes, max_seconds: int = 120) -> np.ndarray:
    try:
        with sf.SoundFile(io.BytesIO(payload)) as source:
            if source.format not in ('WAV', 'WAVEX', 'FLAC', 'OGG', 'MP3'):
                raise ValueError('Supported formats: WAV, FLAC, OGG, MP3')
            if not 8000 <= source.samplerate <= 48000 or not 1 <= source.channels <= 2:
                raise ValueError('Audio must be mono/stereo at 8–48 kHz')
            if source.frames <= 0 or source.frames > max_seconds * source.samplerate:
                raise ValueError(f'Audio duration must be between 0 and {max_seconds} seconds')
            rate = source.samplerate
            data = source.read(dtype='float32', always_2d=True).mean(axis=1)
    except (RuntimeError, sf.LibsndfileError) as error:
        raise ValueError('Cannot decode audio; use PCM WAV, FLAC, OGG or MP3') from error
    if not np.isfinite(data).all():
        raise ValueError('Audio contains non-finite samples')
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        data = resample_poly(data, 16000 // divisor, rate // divisor)
    return np.clip(data, -1, 1).astype(np.float32)
