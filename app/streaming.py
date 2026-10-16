import numpy as np


class SegmentBuffer:
    """FSMN absolute millisecond boundaries → bounded, non-overlapping PCM segments."""
    def __init__(self, max_segment_ms=10000):
        self.data = np.empty(0, dtype=np.float32)
        self.offset = 0
        self.total = 0
        self.active = None
        self.emitted_until = 0
        self.maximum = max_segment_ms * 16

    def append(self, samples):
        self.data = np.concatenate((self.data, samples))
        self.total += len(samples)

    def boundaries(self, pairs, final=False):
        result = []

        def emit(end, reason):
            end = min(self.total, int(end))
            start = max(self.active, self.offset, self.emitted_until)
            while end > start:
                cut = min(end, start + self.maximum)
                result.append((start / 16, cut / 16,
                               self.data[start - self.offset:cut - self.offset].copy(),
                               'max_duration' if cut < end else reason))
                self.emitted_until = cut
                start = cut

        for start_ms, end_ms in pairs:
            if start_ms >= 0:
                self.active = max(int(start_ms * 16), self.offset, self.emitted_until)
            if end_ms >= 0 and self.active is not None:
                emit(end_ms * 16, 'vad')
                self.active = None
        if self.active is not None and self.total - self.active >= self.maximum:
            cut = self.active + self.maximum
            emit(cut, 'max_duration')
            self.active = cut
        if final and self.active is not None:
            emit(self.total, 'stop')
            self.active = None
        keep = self.active if self.active is not None else max(0, self.total - 32000)
        keep = max(self.offset, keep)
        self.data = self.data[keep - self.offset:]
        self.offset = keep
        return result
