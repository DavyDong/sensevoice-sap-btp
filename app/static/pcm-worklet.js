class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer = new Int16Array(1600); this.index = 0;
    this.weight = 0; this.sum = 0; this.ratio = sampleRate / 16000; this.closed = false;
    this.port.onmessage = e => {
      if (e.data === 'flush') {
        this.closed = true;
        if (this.weight > 1e-8) this.output(this.sum / this.weight);
        if (this.index) this.port.postMessage(this.buffer.slice(0, this.index).buffer);
        this.port.postMessage('flushed');
      }
    };
  }
  output(value) {
    this.buffer[this.index++] = Math.round(Math.max(-1, Math.min(1, value)) * 32767);
    if (this.index === 1600) {
      this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
      this.buffer = new Int16Array(1600); this.index = 0;
    }
  }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (!samples || this.closed) return true;
    for (const value of samples) {
      let left = 1;
      while (left > 1e-8) {
        const amount = Math.min(left, this.ratio - this.weight);
        this.sum += value * amount; this.weight += amount; left -= amount;
        if (this.weight >= this.ratio - 1e-8) {
          this.output(this.sum / this.weight); this.sum = 0; this.weight = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm-processor', PCMProcessor);
