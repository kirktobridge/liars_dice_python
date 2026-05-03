(() => {
  const promptsEl = document.getElementById('prompts');
  const responsesEl = document.getElementById('responses');
  const statusEl = document.getElementById('status');
  const statusLabel = statusEl.querySelector('.label');
  const clearBtn = document.getElementById('clear');
  const autoscrollBtn = document.getElementById('autoscroll-toggle');

  let autoscroll = true;
  let currentResponse = null; // active streaming entry (.response element)

  autoscrollBtn.addEventListener('click', () => {
    autoscroll = !autoscroll;
    autoscrollBtn.textContent = `Autoscroll: ${autoscroll ? 'on' : 'off'}`;
  });
  clearBtn.addEventListener('click', () => {
    promptsEl.innerHTML = '';
    responsesEl.innerHTML = '';
    currentResponse = null;
  });

  function fmtTs(ts) {
    const d = new Date(ts * 1000);
    return d.toISOString().split('T')[1].replace('Z', '');
  }
  function scroll(el) {
    if (autoscroll) el.scrollTop = el.scrollHeight;
  }
  function makeEntry(parent, tsHtml, metaHtml = '') {
    const entry = document.createElement('div');
    entry.className = 'entry';
    if (tsHtml) {
      const ts = document.createElement('div');
      ts.className = 'ts';
      ts.textContent = tsHtml;
      entry.appendChild(ts);
    }
    if (metaHtml) {
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = metaHtml;
      entry.appendChild(meta);
    }
    const body = document.createElement('div');
    body.className = 'body';
    entry.appendChild(body);
    parent.appendChild(entry);
    return body;
  }

  function handle(event) {
    const { kind, ts } = event;
    if (kind === 'prompt') {
      const meta = `${event.model}  •  temp=${event.temperature}  •  ${event.streaming ? 'stream' : 'one-shot'}`;
      const body = makeEntry(promptsEl, fmtTs(ts), meta);
      body.textContent = event.prompt;
      scroll(promptsEl);

      // Open a fresh response entry tied to this prompt.
      const respBody = makeEntry(responsesEl, fmtTs(ts));
      respBody.classList.add('response', 'streaming');
      currentResponse = respBody;
      scroll(responsesEl);
      return;
    }
    if (kind === 'token') {
      if (currentResponse == null) {
        currentResponse = makeEntry(responsesEl, fmtTs(ts));
        currentResponse.classList.add('response', 'streaming');
      }
      currentResponse.appendChild(document.createTextNode(event.text));
      scroll(responsesEl);
      return;
    }
    if (kind === 'done') {
      if (currentResponse != null) {
        currentResponse.classList.remove('streaming');
        const done = document.createElement('div');
        done.className = 'done';
        done.textContent = '✓ done';
        currentResponse.parentElement.appendChild(done);
        currentResponse = null;
      }
      scroll(responsesEl);
      return;
    }
    if (kind === 'error') {
      if (currentResponse != null) {
        currentResponse.classList.remove('streaming');
        currentResponse.classList.add('error');
      }
      const err = makeEntry(responsesEl, fmtTs(ts));
      err.classList.add('error');
      err.textContent = `✗ ${event.message}`;
      currentResponse = null;
      scroll(responsesEl);
      return;
    }
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/llm-debug`);
    ws.addEventListener('open', () => {
      statusEl.classList.add('connected');
      statusLabel.textContent = 'connected';
    });
    ws.addEventListener('close', () => {
      statusEl.classList.remove('connected');
      statusLabel.textContent = 'disconnected — retrying…';
      setTimeout(connect, 1500);
    });
    ws.addEventListener('error', () => ws.close());
    ws.addEventListener('message', (msg) => {
      try {
        handle(JSON.parse(msg.data));
      } catch (e) {
        console.error('bad message', e, msg.data);
      }
    });
  }
  connect();
})();
