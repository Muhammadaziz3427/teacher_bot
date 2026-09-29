/* Dashboard page test: runs miniapp/index.html's inline JS on a stubbed DOM.
 *
 *   node tests/miniapp_page.test.js
 *
 * No browser needed — it catches the mistakes that would otherwise only show
 * up as a blank page in Telegram (broken picker, escaping, 401 handling).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'miniapp', 'index.html'), 'utf8');
const match = html.match(/<script>\s*([\s\S]*?)<\/script>/);
if (!match) {
  console.log('FAIL: inline script not found');
  process.exit(1);
}
const code = match[1];

function run(search, fetchImpl) {
  const store = {};
  const sandbox = {
    location: { search },
    document: {
      getElementById: (id) => (store[id] = store[id] || { textContent: '', innerHTML: '' }),
      title: '',
    },
    window: {},
    fetch: fetchImpl,
    setInterval: () => {},
    setTimeout,
    console,
    URLSearchParams,
    encodeURIComponent,
    Math,
    JSON,
    String,
    Number,
    Object,
    Array,
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return store;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const checks = [];
const check = (label, ok, detail = '') => {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ' — ' + detail : ''}`);
  checks.push(ok);
};

async function main() {
  // --- scenario 1: bare URL (no ?chat) → group picker -------------------
  const groupCalls = [];
  const groups = run('', async (url) => {
    groupCalls.push(url);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        groups: [
          { id: -1001234567890, title: 'English B1 <Group>', students: 3, active_homeworks: 1 },
        ],
      }),
    };
  });
  await sleep(50);
  check('bare URL asks for the group list', groupCalls.some((u) => u.includes('/api/groups')));
  check('picker links to the group dashboard',
    groups.rows.innerHTML.includes('?chat=-1001234567890&token='),
    groups.rows.innerHTML.slice(0, 60));
  check('group titles are HTML-escaped',
    groups.rows.innerHTML.includes('English B1 &lt;Group&gt;'));
  check('picker shows the student count',
    groups.rows.innerHTML.includes('3 students'));

  // --- scenario 2: ?chat= present → weekly dashboard --------------------
  const summaryCalls = [];
  const dash = run('?chat=-1001234567890&token=abc', async (url) => {
    summaryCalls.push(url);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        group: { id: -1001234567890, title: 'English B1' },
        period: { start: '2026-09-24', end: '2026-09-30' },
        students: [{ id: 101, name: 'Aziza', points: 4, attendance: 90, submitted: 2 }],
        active_homeworks: [{ id: 3, title: 'Unit 5', due: '01.10 14:00' }],
        totals: { students: 1, active_homeworks: 1, submitted: 2, avg_score: 78 },
      }),
    };
  });
  await sleep(50);
  check('dashboard asks for the summary',
    summaryCalls.some((u) => u.includes('/api/summary') && u.includes('chat=-1001234567890')));
  check('dashboard renders the student row', dash.rows.innerHTML.includes('Aziza'));
  check('dashboard renders the score card', dash.cards.innerHTML.includes('78'));
  check('dashboard renders the active homework', dash.hw.innerHTML.includes('Unit 5'));

  // --- scenario 3: 401 gives an actionable message ----------------------
  const broken = run('', async () => ({ ok: false, status: 401, json: async () => ({}) }));
  await sleep(50);
  check('401 explains how to fix MINIAPP_TOKEN',
    broken.rows.innerHTML.includes('MINIAPP_TOKEN'),
    broken.rows.innerHTML.slice(0, 80));

  process.exit(checks.every(Boolean) ? 0 : 1);
}

main();