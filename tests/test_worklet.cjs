// Signal contract tests; no microphone device or browser permission is used here.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('app/static/pcm-worklet.js', 'utf8');
for (const rate of [16000, 44100, 48000]) {
  let Processor;
  const messages = [];
  const sandbox = {sampleRate:rate, Int16Array, Math,
    AudioWorkletProcessor:class {constructor() {this.port={postMessage(value) {messages.push(value);}};}},
    registerProcessor(name, type) {Processor=type;}};
  vm.runInNewContext(source, sandbox);
  const worklet = new Processor();
  for (let start=0; start<rate; start+=128) {
    const input = Float32Array.from({length:Math.min(128, rate-start)}, (_,i)=>Math.sin(2*Math.PI*440*(start+i)/rate)*.8);
    worklet.process([[input]]);
  }
  worklet.port.onmessage({data:'flush'});
  const chunks=messages.filter(value => value !== 'flushed');
  assert.equal(chunks.reduce((n,b)=>n+b.byteLength/2,0),16000,`sample count at ${rate}`);
  assert.equal(messages.at(-1),'flushed');
  const pcm = chunks.flatMap(b=>Array.from(new Int16Array(b)));
  assert(Math.max(...pcm)>25000 && Math.max(...pcm)<=26214);
  assert(chunks.every(b=>b.byteLength<=3200));
}
console.log('AudioWorklet: 16 / 44.1 / 48 kHz signal, frame size and flush checks passed.');
