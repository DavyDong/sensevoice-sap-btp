const $ = id => document.getElementById(id);
let ws, context, media, processor, queue = [], inFlight = 0, flushed = false, stopSent = false, timer;
function status(text) { $('status').textContent = text; }
function busy(value) { $('upload').disabled = value; $('start').disabled = value; $('language').disabled = value; }
function cleanup() {
  clearTimeout(timer); media?.getTracks().forEach(track => track.stop()); media = null;
  processor?.disconnect(); processor = null;
  context?.close(); context = null;
  if (ws && ws.readyState < 2) ws.close(); ws = null;
  queue = []; inFlight = 0; flushed = false; stopSent = false;
  busy(false); $('stop').disabled = true;
}
function fail(message) { status(message); cleanup(); }
function pump() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  while (queue.length && inFlight < 8) { ws.send(queue.shift()); inFlight += 1; }
  if (!queue.length && !inFlight && flushed && !stopSent) { stopSent = true; ws.send(JSON.stringify({type:'stop'})); }
}
$('upload').onclick = async () => {
  const file = $('audio').files[0];
  if (!file) return status('请先选择一个音频文件。');
  if (file.size >= 20 * 1024 * 1024) return status('文件太大，请选择小于 20 MiB 的音频。');
  busy(true); status('正在识别文件…'); $('result').textContent = ''; $('metrics').textContent = '';
  try {
    const body = new FormData(); body.append('file', file); body.append('language', $('language').value);
    const token = $('token').value.trim();
    const response = await fetch('/v1/audio/transcriptions', {method:'POST', body, headers:token ? {Authorization:`Bearer ${token}`} : {}});
    const result = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(result.detail));
    $('result').textContent = result.text || '未检测到可识别的语音。';
    $('metrics').textContent = `音频 ${result.audio_seconds} 秒 · 推理 ${result.inference_seconds} 秒 · RTF ${result.rtf}`;
    status('文件识别完成。');
  } catch (error) { status(`识别失败：${error.message}`); }
  finally { busy(false); }
};
$('start').onclick = async () => {
  busy(true); $('result').textContent = ''; $('metrics').textContent = ''; status('正在连接服务…');
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('麦克风需要 localhost 或 HTTPS 地址。');
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/v1/stream`);
    ws = socket;
    timer = setTimeout(() => fail('服务连接超时。'), 15000);
    socket.onopen = () => socket.send(JSON.stringify({type:'start', format:'pcm_s16le', sample_rate:16000,
      language:$('language').value, token:$('token').value.trim()}));
    socket.onerror = () => { if (ws === socket) fail('连接失败，请检查服务地址和访问令牌。'); };
    socket.onclose = event => { if (ws === socket) fail(`会话已关闭（${event.code}），请重新开始。`); };
    socket.onmessage = async event => {
      if (ws !== socket) return;
      const message = JSON.parse(event.data);
      if (message.type === 'ready') {
        clearTimeout(timer);
        try {
          const capture = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true}});
          if (ws !== socket || socket.readyState !== WebSocket.OPEN) { capture.getTracks().forEach(t => t.stop()); return; }
          media = capture;
          context = new AudioContext({sampleRate:16000}); await context.resume();
          await context.audioWorklet.addModule('/static/pcm-worklet.js');
          processor = new AudioWorkletNode(context, 'pcm-processor');
          processor.port.onmessage = e => {
            if (e.data === 'flushed') { flushed = true; pump(); return; }
            queue.push(e.data);
            if (queue.length + inFlight > 20) return fail('识别速度跟不上录音，已停止。请检查网络或服务负载后重试。');
            pump();
          };
          const source = context.createMediaStreamSource(media); source.connect(processor);
          const mute = context.createGain(); mute.gain.value = 0; processor.connect(mute).connect(context.destination);
          $('stop').disabled = false; status('正在录音，请说话；停顿后会显示文字。');
          timer = setTimeout(() => $('stop').click(), (message.max_session_seconds - 5) * 1000);
        } catch(error) { if (ws === socket) fail(`无法使用麦克风：${error.message}`); }
      } else if (message.type === 'segment') {
        $('result').textContent += ($('result').textContent ? '\n' : '') + message.text;
        $('metrics').textContent = `已收到 ${message.sequence} 段 · 片段 ${Math.round(message.start_ms)}–${Math.round(message.end_ms)} ms`;
      } else if (message.type === 'ack') { inFlight = Math.max(0, inFlight - 1); pump(); }
      else if (message.type === 'done') { status('录音识别完成。'); cleanup(); }
      else if (message.type === 'error') fail(message.detail);
    };
  } catch(error) { fail(error.message); }
};
$('stop').onclick = () => {
  $('stop').disabled = true; clearTimeout(timer); status('正在处理最后一段…');
  processor?.port.postMessage('flush');
  media?.getTracks().forEach(track => track.stop());
  timer = setTimeout(() => fail('尾段处理超时，请查看已返回的文字。'), 60000);
};
$('copy').onclick = async () => {
  try { await navigator.clipboard.writeText($('result').textContent); status('已复制。'); }
  catch { status('无法自动复制，请选中文字后复制。'); }
};
fetch('/health/ready').then(r => status(r.ok ? '服务就绪，可以开始识别。' : '模型尚未就绪，请稍后刷新。')).catch(() => status('服务未连接。'));
window.addEventListener('pagehide', cleanup);
