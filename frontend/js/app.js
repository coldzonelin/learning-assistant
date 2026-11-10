import { checkConnection } from './api.js';

const pages = [...document.querySelectorAll('.page')];
const links = [...document.querySelectorAll('.main-nav a')];

function showPage() {
  const route = location.hash.slice(1);
  const active = pages.some(page => page.id === route) ? route : 'study';
  pages.forEach(page => { page.hidden = page.id !== active; });
  links.forEach(link => {
    if (link.hash === `#${active}`) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

async function updateConnection() {
  const online = await checkConnection();
  const dot = document.querySelector('#connection-dot');
  dot.className = `connection-dot ${online ? 'online' : 'offline'}`;
  document.querySelector('#connection-label').textContent = online ? '后台已连接' : '后台未连接';
}

window.addEventListener('hashchange', showPage);
showPage();
updateConnection();
setInterval(updateConnection, 30000);

import "./chat.js";
import './library.js';
import './assessment.js';
import './progress.js';
import './reports.js';
