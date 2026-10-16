const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const elements = {};
const sandbox = {document:{getElementById:id => elements[id] ||= {}}, WebSocket:{OPEN:1},
  window:{addEventListener(){}},fetch:()=>Promise.resolve({ok:true}),setTimeout,clearTimeout};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../app/static/app.js'),'utf8'), sandbox);
vm.runInContext(`
  let sent=[];
  ws={readyState:1,send:data=>sent.push(data)};
  queue=Array.from({length:12},(_,i)=>i); inFlight=0; flushed=true; stopSent=false;
  pump();
`,sandbox);
assert.equal(vm.runInContext('sent.length',sandbox),8,'Fill the window without awaiting each RTT');
assert.equal(vm.runInContext('queue.length',sandbox),4);
assert.equal(vm.runInContext('stopSent',sandbox),false);
vm.runInContext('for(let i=0;i<4;i++){inFlight--;pump()}',sandbox);
assert.equal(vm.runInContext('sent.length',sandbox),12);
assert.equal(vm.runInContext('stopSent',sandbox),false,'Stop waits until all audio is acknowledged');
vm.runInContext('for(let i=0;i<8;i++){inFlight--;pump()}',sandbox);
assert.equal(vm.runInContext('sent.length',sandbox),13);
assert.equal(vm.runInContext('sent[12]',sandbox),JSON.stringify({type:'stop'}));
vm.runInContext('pump()',sandbox);
assert.equal(vm.runInContext('sent.length',sandbox),13,'Only one stop message');
console.log('Browser bounded window and stop/ACK drain passed');
