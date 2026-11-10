import { request, getAllPages } from './api.js';
const input = document.querySelector('#file-input'), zone = document.querySelector('#upload-zone'), list = document.querySelector('#material-list'), notice = document.querySelector('#library-notice');
const formats = /\.(pdf|ppt|pptx|doc|docx|md|markdown|txt)$/i;
function size(bytes) { if (bytes == null) return '—'; if (bytes < 1024) return `${bytes} B`; if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / 1048576).toFixed(1)} MB`; }
function cell(row, value) { const td = row.insertCell(); td.textContent = value; return td; }
async function refresh() {
  try {
    const items = await getAllPages('/materials'); list.replaceChildren();
    if (!items.length) { const row = list.insertRow(); const td = cell(row, '暂无资料'); td.colSpan = 5; }
    for (const item of items) {
      const row = list.insertRow(); cell(row, item.name); cell(row, (item.file_type || '—').toUpperCase()); cell(row, size(item.file_size ?? item.size)); cell(row, ({ processing:'解析中', ready:'完成', failed:'失败' })[item.status] || '未知');
      const actions = row.insertCell();
      if (item.status === 'failed') { const retry = document.createElement('button'); retry.className = 'link-button'; retry.textContent = '重试'; retry.onclick = async () => { retry.disabled = true; try { const result = await request(`/materials/${encodeURIComponent(item.id)}/retry`, {method:'POST'}); notice.textContent = result.status === 'failed' ? `解析失败：${result.failure_reason || '未知原因'}` : result.status === 'ready' ? '解析完成。' : '已重新开始解析。'; await refresh(); } catch { notice.textContent = '重试失败，请检查后台连接。'; retry.disabled = false; } }; actions.append(retry); }
      const remove = document.createElement('button'); remove.className = 'link-button'; remove.textContent = '删除'; remove.onclick = async () => { if (!confirm(`确定删除“${item.name}”吗？`)) return; remove.disabled = true; try { await request(`/materials/${encodeURIComponent(item.id)}`, {method:'DELETE'}); notice.textContent = '资料已删除。'; await refresh(); } catch { notice.textContent = '删除失败，请检查后台是否支持删除接口。'; remove.disabled = false; } }; actions.append(remove);
    }
  } catch { list.replaceChildren(); const row = list.insertRow(); const td = cell(row, '资料加载失败，请检查后台连接。'); td.colSpan = 5; }
}
async function upload(files) {
  const messages = [];
  for (const file of files) {
    if (!formats.test(file.name)) { messages.push(`${file.name}：不支持的格式`); continue; }
    const body = new FormData(); body.append('file', file);
    try { const result = await request('/materials', {method:'POST',body}); messages.push(result.status === 'failed' ? `${file.name}：上传成功，解析失败（${result.failure_reason || '未知原因'}）` : `${file.name}：上传成功`); }
    catch { messages.push(`${file.name}：上传失败`); }
  }
  notice.textContent = messages.join('；'); input.value = ''; await refresh();
}
input.addEventListener('change', () => upload(input.files));
for (const event of ['dragenter','dragover']) zone.addEventListener(event, e => { e.preventDefault(); zone.classList.add('dragging'); });
for (const event of ['dragleave','drop']) zone.addEventListener(event, e => { e.preventDefault(); zone.classList.remove('dragging'); });
zone.addEventListener('drop', e => upload(e.dataTransfer.files));
window.addEventListener('hashchange', () => { if (location.hash === '#library') refresh(); });
if (location.hash === '#library') refresh();
