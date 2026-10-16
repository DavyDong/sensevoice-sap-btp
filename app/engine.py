import os
import threading
import time

import numpy as np

from .streaming import SegmentBuffer


class Engine:
    def __init__(self, settings):
        # Network access is not part of serving: download models explicitly before starting.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        import torch
        from funasr import AutoModel
        torch.set_num_threads(settings.threads)
        torch.set_num_interop_threads(1)
        self.lock = threading.RLock()
        self.settings = settings
        root = settings.model_root.resolve()
        for directory in ('sensevoice', 'vad'):
            if not (root / directory / 'model.pt').is_file():
                raise FileNotFoundError('Models missing. Run: python scripts/download_models.py')
        options = dict(device='cpu', disable_update=True, disable_pbar=True,
                       disable_log=True, trust_remote_code=False, ncpu=settings.threads)
        self.asr = AutoModel(model=str(root / 'sensevoice'), **options)
        self.vad = AutoModel(model=str(root / 'vad'), max_end_silence_time=600,
                             max_single_segment_time=settings.max_segment_ms, **options)

    def recognize(self, samples, language):
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        if len(samples) < 1600 or np.max(np.abs(samples)) < 1e-5:
            return ''
        with self.lock:
            result = self.asr.generate(input=samples, cache={}, language=language,
                                       use_itn=True, batch_size_s=10, disable_pbar=True)
        return rich_transcription_postprocess(result[0]['text']) if result else ''

    def transcribe(self, samples, language='auto'):
        started = time.perf_counter()
        with self.lock:
            detected = self.vad.generate(input=samples, cache={}, is_final=True,
                                         max_end_silence_time=600,
                                         max_single_segment_time=self.settings.max_segment_ms,
                                         disable_pbar=True)
            pairs = detected[0].get('value', []) if detected else []
            segments = []
            for start, end in pairs:
                for left in range(int(start * 16), min(len(samples), int(end * 16)), self.settings.max_segment_ms * 16):
                    right = min(int(end * 16), left + self.settings.max_segment_ms * 16, len(samples))
                    text = self.recognize(samples[left:right], language)
                    if text:
                        segments.append(dict(start_ms=left / 16, end_ms=right / 16, text=text))
        elapsed = time.perf_counter() - started
        duration = len(samples) / 16000
        return dict(text=' '.join(s['text'] for s in segments), segments=segments,
                    audio_seconds=round(duration, 3), inference_seconds=round(elapsed, 3),
                    rtf=round(elapsed / duration, 3), language=language)

    def new_stream(self, language='auto'):
        return Stream(self, language)


class Stream:
    def __init__(self, engine, language):
        self.engine = engine
        self.language = language
        self.cache = {}
        self.buffer = SegmentBuffer(engine.settings.max_segment_ms)
        self.pending = bytearray()
        self.sequence = 0

    def feed(self, raw: bytes, final=False):
        self.pending.extend(raw)
        output = []
        with self.engine.lock:
            while len(self.pending) >= 3200 or (final and self.pending):
                count = min(3200, len(self.pending))
                chunk = bytes(self.pending[:count])
                del self.pending[:count]
                samples = np.frombuffer(chunk, dtype='<i2').astype(np.float32) / 32768
                self.buffer.append(samples)
                vad_samples = np.pad(samples, (0, 1600 - len(samples))) if len(samples) < 1600 else samples
                output.extend(self._detect(vad_samples, False))
            if final:
                # Flush streaming VAD using a short silence frame; do not add it to audio time.
                output.extend(self._detect(np.zeros(1600, dtype=np.float32), True))
        return output

    def _detect(self, samples, final):
        found = self.engine.vad.generate(input=samples, cache=self.cache, is_final=final,
                                         chunk_size=100, max_end_silence_time=600,
                                         max_single_segment_time=self.engine.settings.max_segment_ms,
                                         disable_pbar=True)
        pairs = found[0].get('value', []) if found else []
        output = []
        for start, end, audio, reason in self.buffer.boundaries(pairs, final=final):
            text = self.engine.recognize(audio, self.language)
            if text:
                self.sequence += 1
                output.append(dict(type='segment', sequence=self.sequence, start_ms=start,
                                   end_ms=end, text=text, final=True, reason=reason))
        return output
