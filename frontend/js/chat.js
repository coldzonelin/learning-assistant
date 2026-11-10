import { createConversation, getAllPages, sendMessage } from './api.js';

const select = document.querySelector('#material-select');
const history = document.querySelector('#history-list');
const messages = document.querySelector('#chat-messages');
const empty = document.querySelector('#chat-empty');
const input = document.querySelector('#chat-input');
const form = document.querySelector('#chat-form');
const submit = document.querySelector('#send-message');
const reset = document.querySelector('#new-conversation');
const notice = document.querySelector('#chat-notice');
const thinking = document.querySelector('#thinking');
let currentId = null;
let conversations = [];
let busy = false;

function setNotice(message = '') {
  notice.textContent = message;
  notice.hidden = !message;
}
function setBusy(value) {
  busy = value;
  input.disabled = value;
  submit.disabled = value;
  select.disabled = value;
  reset.disabled = value;
  history.querySelectorAll('button').forEach(button => { button.disabled = value; });
  thinking.hidden = !value;
}
function clearMessages() {
  messages.replaceChildren(empty);
  empty.hidden = false;
}
function inlineText(parent, text) {
  // Render Markdown as DOM nodes, never as HTML supplied by the model.
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 1) {
      const code = document.createElement('code'); code.textContent = part.slice(1, -1); parent.append(code);
    } else if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      const strong = document.createElement('strong'); strong.textContent = part.slice(2, -2); parent.append(strong);
    } else parent.append(document.createTextNode(part));
  }
}
function renderMarkdown(container, content) {
  const lines = String(content || '').replace(/\r\n/g, '\n').split('\n');
  let list = null, paragraph = null, code = null;
  for (const line of lines) {
    if (/^\s*```/.test(line)) {
      if (code) { code = null; } else { const pre = document.createElement('pre'); code = document.createElement('code'); pre.append(code); container.append(pre); }
      list = null; paragraph = null; continue;
    }
    if (code) { code.textContent += (code.textContent ? '\n' : '') + line; continue; }
    if (!line.trim()) { list = null; paragraph = null; continue; }
    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
    const item = line.match(/^\s*(?:([-*+])\s+|(\d+)\.\s+)(.+)$/);
    if (heading) { const h = document.createElement(`h${Math.min(heading[1].length, 6)}`); inlineText(h, heading[2]); container.append(h); list = null; paragraph = null; }
    else if (item) {
      const type = item[2] ? 'OL' : 'UL';
      if (!list || list.tagName !== type) { list = document.createElement(type); container.append(list); }
      const li = document.createElement('li'); inlineText(li, item[3]); list.append(li); paragraph = null;
    } else {
      list = null;
      if (!paragraph) { paragraph = document.createElement('p'); container.append(paragraph); }
      else paragraph.append(document.createTextNode('\n'));
      inlineText(paragraph, line);
    }
  }
}
function addMessage(message) {
  empty.hidden = true;
  const article = document.createElement('article');
  article.className = `message ${message.role === 'user' ? 'user' : 'assistant'}`;
  if (message.role === 'user') article.textContent = message.content;
  else {
    const body = document.createElement('div'); body.className = 'message-body'; renderMarkdown(body, message.content); article.append(body);
    const sources = Array.isArray(message.sources) ? message.sources : [];
    if (sources.length) {
      const details = document.createElement('details'); details.className = 'sources';
      const summary = document.createElement('summary'); summary.textContent = `查看引用资料（${sources.length}）`; details.append(summary);
      for (const source of sources) {
        const item = document.createElement('div'); item.className = 'source-item';
        const title = document.createElement('strong'); title.textContent = [source.material_name || '资料', source.page_number != null ? `第 ${source.page_number} 页` : '', source.section_title || ''].filter(Boolean).join(' · ');
        const excerpt = document.createElement('p'); excerpt.textContent = source.excerpt || '暂无片段内容'; item.append(title, excerpt); details.append(item);
      }
      article.append(details);
    }
  }
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}
function renderHistory() {
  history.replaceChildren();
  if (!conversations.length) { const p = document.createElement('p'); p.className = 'history-hint'; p.textContent = '还没有历史对话'; history.append(p); return; }
  for (const conversation of conversations) {
    const button = document.createElement('button'); button.type = 'button'; button.className = `history-item${conversation.id === currentId ? ' active' : ''}`;
    button.textContent = conversation.title || (conversation.created_at ? `对话 · ${new Date(conversation.created_at).toLocaleString('zh-CN')}` : `对话 ${conversation.id}`);
    button.title = button.textContent; button.disabled = busy;
    button.addEventListener('click', () => openConversation(conversation)); history.append(button);
  }
}
async function loadHistory() {
  conversations = await getAllPages('/conversations');
  renderHistory();
}
async function loadMaterials() {
  const materials = await getAllPages('/materials?status=ready');
  const selected = select.value;
  select.replaceChildren(new Option('普通对话 · 不引用资料', ''));
  for (const material of materials.filter(item => item.status === 'ready')) select.add(new Option(material.name, material.id));
  if (selected && ![...select.options].some(option => option.value === selected)) select.add(new Option('原资料不可用', selected));
  select.value = selected;
}
async function openConversation(conversation) {
  if (busy) return;
  setBusy(true); setNotice();
  try {
    if (!Array.isArray(conversation.material_ids)) throw new Error('历史对话缺少资料范围');
    const loaded = await getAllPages(`/conversations/${encodeURIComponent(conversation.id)}/messages`);
    currentId = conversation.id;
    const materialId = conversation.material_ids?.[0] || '';
    if (materialId && ![...select.options].some(option => option.value === materialId)) select.add(new Option('原资料不可用', materialId));
    select.value = materialId;
    clearMessages(); loaded.forEach(addMessage); renderHistory();
  } catch (error) { setNotice(error.message === '历史对话缺少资料范围' ? '无法恢复该对话：后台未返回资料范围。' : '无法加载历史对话，请检查后台连接后重试。'); }
  finally { setBusy(false); }
}
function newConversation() { currentId = null; clearMessages(); setNotice(); input.value = ''; renderHistory(); input.focus(); }
reset.addEventListener('click', newConversation);
select.addEventListener('change', newConversation);
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  const content = input.value.trim();
  if (!content || busy) return;
  setBusy(true); setNotice();
  const pendingMessage = addMessage({ role: 'user', content });
  try {
    if (!currentId) { const conversation = await createConversation(select.value ? [select.value] : []); currentId = conversation.id; }
    const result = await sendMessage(currentId, content);
    pendingMessage.textContent = result.user_message.content;
    addMessage({ role: 'assistant', ...result.assistant_message });
    input.value = '';
    try { await loadHistory(); } catch { setNotice('消息已发送，但历史对话列表加载失败。'); }
  } catch { pendingMessage.remove(); if (!messages.querySelector('.message')) empty.hidden = false; setNotice('发送失败，请检查后台连接后重试。输入内容已保留。'); }
  finally { setBusy(false); input.focus(); }
});
Promise.allSettled([loadMaterials(), loadHistory()]).then(results => {
  if (results.some(result => result.status === 'rejected')) {
    if (results[1].status === 'rejected') { history.replaceChildren(); const p = document.createElement('p'); p.className = 'history-hint'; p.textContent = '历史对话暂时无法加载'; history.append(p); }
    setNotice('资料或历史对话加载失败，请检查后台连接。');
  }
});

window.addEventListener('hashchange', () => { if (location.hash === '#study') loadMaterials().catch(() => setNotice('资料加载失败，请检查后台连接。')); });
