const API_BASE = '/api/v1';

export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(`请求失败：${response.status}`);
  const result = await response.json();
  if (result.error) throw new Error(result.error.message || '请求失败');
  return result.data;
}

export async function checkConnection() {
  try {
    const data = await request('/materials?page=1&page_size=1', { cache: 'no-store' });
    return Array.isArray(data?.items);
  } catch {
    return false;
  }
}

export function createConversation(materialIds) {
  return request('/conversations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ material_ids: materialIds }) });
}

export function sendMessage(id, content) {
  return request(`/conversations/${encodeURIComponent(id)}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
}

export async function getAllPages(path) {
  const items = [];
  let page = 1;
  while (true) {
    const separator = path.includes('?') ? '&' : '?';
    const result = await request(`${path}${separator}page=${page}&page_size=100`);
    if (!Array.isArray(result?.items)) throw new Error('返回的数据格式不正确');
    items.push(...result.items);
    if (items.length >= result.total || result.items.length === 0) return items;
    if (!Number.isFinite(result.total)) throw new Error('分页数据缺少总数');
    page++;
  }
}
