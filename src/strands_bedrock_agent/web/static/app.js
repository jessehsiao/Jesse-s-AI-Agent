// app.js — vanilla JS, no framework
'use strict';

const form = document.getElementById('prompt-form');
const input = document.getElementById('prompt-input');
const sendBtn = document.getElementById('send-btn');
const transcript = document.getElementById('transcript');
const toolInvocations = document.getElementById('tool-invocations');
const status = document.getElementById('status');

/**
 * Toggle busy state: disable/enable input and send button, show/hide status.
 * @param {boolean} busy
 */
function setBusy(busy) {
  sendBtn.disabled = busy;
  input.disabled = busy;
  status.hidden = !busy;
}

/**
 * Append a user message bubble to the transcript.
 * @param {string} text
 */
function appendUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message user-message';
  div.textContent = text;
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
}

/**
 * Append an agent response bubble to the transcript.
 * @param {string} text
 */
function appendAgentMessage(text) {
  const div = document.createElement('div');
  div.className = 'message agent-message';
  div.textContent = text;
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
}

/**
 * Append an error message to the transcript.
 * @param {string} text
 */
function appendErrorMessage(text) {
  const div = document.createElement('div');
  div.className = 'message error-message';
  div.textContent = text;
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
}

/**
 * Append a tool invocation chip/badge to the tool-invocations container.
 * @param {string} toolName
 * @param {string} startedAt
 */
function appendToolChip(toolName, startedAt) {
  const chip = document.createElement('span');
  chip.className = 'tool-chip';
  chip.textContent = toolName + ' @ ' + startedAt;
  toolInvocations.appendChild(chip);
}

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;

  appendUserMessage(prompt);
  input.value = '';
  toolInvocations.innerHTML = '';
  setBusy(true);

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 120_000);

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
      signal: ac.signal,
    });
    const body = await resp.json();
    if (!resp.ok) {
      appendErrorMessage(body.error || 'HTTP ' + resp.status);
    } else {
      appendAgentMessage(body.response);
      for (const inv of body.tool_invocations) {
        appendToolChip(inv.tool_name, inv.started_at);
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      appendErrorMessage('Request timed out after 120 seconds');
    } else {
      appendErrorMessage(err.message);
    }
  } finally {
    clearTimeout(timer);
    setBusy(false);
  }
});
