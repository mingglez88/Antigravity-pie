const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const source = fs.readFileSync(path.join(__dirname, '../assets/antigravity-hans-overlay.js'), 'utf8');
const pause = () => new Promise(resolve => setTimeout(resolve, 15));
async function settle(window) {
  for (let i = 0; i < 150; i++) {
    await pause();
    if (window.__antigravityZhPatchError) throw new Error(window.__antigravityZhPatchError);
    if (window.__antigravityZhPatchInstalled) { await pause(); return; }
  }
  throw new Error('overlay not ready');
}
async function fixture(html, url = 'https://127.0.0.1:1234/') {
  const dom = new JSDOM(html, { url, runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.eval(source);
  await settle(dom.window);
  return dom;
}

test('UI translates while code, input, names and response prose remain intact', async () => {
  const dom = await fixture(`<button id="save">Save</button><div class="monaco-workbench"><div role="menu">Settings</div></div>
    <pre id="code">Save Read Settings</pre><div class="monaco-editor">Save</div>
    <textarea placeholder="Search">Save</textarea><div contenteditable="true">Save</div>
    <aside><div data-testid="conversation-row-sidebar"><span id="name">Read</span><button>Delete</button><span class="text-xs">just now</span></div></aside>
    <section aria-label="Agent response"><p id="reply" class="truncate">Save</p><button>Copy</button></section>`);
  try {
    const d = dom.window.document;
    assert.equal(d.querySelector('#save').textContent, '保存');
    assert.equal(d.querySelector('[role=menu]').textContent, '设置');
    assert.equal(d.querySelector('#code').textContent, 'Save Read Settings');
    assert.equal(d.querySelector('#name').textContent, 'Read');
    assert.equal(d.querySelector('#reply').textContent, 'Save');
    assert.equal(d.querySelector('textarea').value, 'Save');
    assert.notEqual(d.querySelector('textarea').placeholder, 'Search');
    assert.equal(d.querySelector('[contenteditable]').textContent, 'Save');
    assert.notEqual(d.querySelector('section button').textContent, 'Copy');
  } finally { dom.window.close(); }
});

test('dynamic text, data-placeholder and late container identity are processed', async () => {
  const dom = await fixture('<div id="late"><span>Save</span></div>', 'https://127.0.0.1:1234/workbench.html');
  try {
    const element = dom.window.document.querySelector('#late');
    assert.equal(element.textContent, 'Save');
    element.className = 'settings-editor';
    element.setAttribute('data-placeholder', 'Search');
    await pause(); await pause();
    assert.equal(element.textContent, '保存');
    assert.notEqual(element.getAttribute('data-placeholder'), 'Search');
    element.firstChild.firstChild.nodeValue = 'Delete';
    await pause(); await pause();
    assert.notEqual(element.textContent, 'Delete');
  } finally { dom.window.close(); }
});

test('stable unknown English is cached; there is no periodic full-document scan', async () => {
  const dom = await fixture('<div>Unknown project-specific label 12345</div>');
  try {
    const w = dom.window;
    const before = { ...w.__antigravityZhMetrics };
    for (let i = 0; i < 10; i++) w.document.dispatchEvent(new w.Event('visibilitychange'));
    await pause(); await pause();
    assert.equal(w.__antigravityZhMetrics.translations, before.translations);
    // Legacy pure translation would evaluate once per call; cached repeated input avoids >99%.
    const start = w.__antigravityZhMetrics.translations;
    for (let i = 0; i < 1000; i++) w.__antigravityZhTranslate('Another previously unknown label');
    assert.equal(w.__antigravityZhMetrics.translations - start, 1);
    const visited = w.__antigravityZhMetrics.visited;
    await new Promise(resolve => setTimeout(resolve, 2100));
    assert.equal(w.__antigravityZhMetrics.visited, visited);
  } finally { dom.window.close(); }
});

test('large DOM yields, prunes code, and cleanup cancels all queued work', async () => {
  const dom = await fixture('<button>Save</button>' + '<div>Zyxqv unrecognized label 12345</div>'.repeat(800) +
                            '<pre>' + '<span>Skip</span>'.repeat(800) + '</pre>');
  try {
    const w = dom.window;
    assert.ok(w.__antigravityZhMetrics.yields > 0);
    assert.ok(w.__antigravityZhMetrics.visited < 2300, 'code subtree was not pruned');
    const first = w.__antigravityZhPatchCleanup;
    w.eval(source);
    assert.equal(w.__antigravityZhPatchCleanup, first);
    w.__antigravityZhPatchRequestedFingerprint = 'new-version';
    w.eval(source);
    await settle(w);
    assert.notEqual(w.__antigravityZhPatchCleanup, first);
    w.__antigravityZhPatchCleanup();
    const before = w.__antigravityZhMetrics.visited;
    w.document.body.appendChild(w.document.createTextNode('Save'));
    w.document.dispatchEvent(new w.Event('visibilitychange'));
    await pause(); await pause();
    assert.equal(w.__antigravityZhMetrics.visited, before);
    assert.equal(w.__antigravityZhPatchInstalled, false);
  } finally { dom.window.close(); }
});

test('permission targets and project names survive repeated translation', async () => {
  const dom = await fixture('<div></div>');
  try {
    const translate = dom.window.__antigravityZhTranslate;
    for (const name of ['Save 10 files', '/tmp/Read 30 minutes.txt', "echo '$&'", 'Last 7 days']) {
      const deletion = translate(`Permanently delete ${name} including 2 active conversations.`);
      assert.ok(deletion.includes(name));
      assert.equal(translate(deletion), deletion);
      const permission = translate(`Requesting permission to read access to this path ${name}`);
      assert.ok(permission.includes(name));
      assert.equal(translate(permission), permission);
    }
  } finally { dom.window.close(); }
});
