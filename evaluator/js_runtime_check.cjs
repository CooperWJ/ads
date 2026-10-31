/**
 * Limited DOM-contract check for the M0 fictional app, using real HTTP requests.
 * This is NOT Chromium, a web security sandbox, or a replacement for Playwright.
 * Evaluator-owned expectations are separate from candidate code.
 */
'use strict';
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');

const [scriptPath, baseURL, testMode] = process.argv.slice(2);
const EXPECTED = Object.freeze({
  title: 'Project Echo', category: 'Research', phase: 'Planning', owner: 'Mira',
  milestone_start: '2026-01-12', milestone_end: '2026-07-18', reference_code: 'DEMO-E01'
});

function fakePage() {
  const ids = new Map();
  const fields = new Map();
  class Element {
    constructor() {
      this.textContent = ''; this.value = ''; this.hidden = false;
      this.disabled = false; this.children = []; this.events = new Map();
    }
    addEventListener(event, handler) { this.events.set(event, handler); }
    append(child) { this.children.push(child); }
  }
  for (const id of ['project-select','project-details','message','error','export','notes','save']) ids.set(id, new Element());
  ids.get('project-details').hidden = true;
  ids.get('error').hidden = true;
  ids.get('export').disabled = true;
  for (const name of Object.keys(EXPECTED)) fields.set(name, new Element());
  const document = {
    getElementById: (id) => ids.get(id) || null,
    createElement: () => new Element(),
    querySelector: (selector) => {
      const match = selector.match(/^\[data-field="([a-z_]+)"\]$/);
      return match ? fields.get(match[1]) || null : null;
    }
  };
  const window = { location: { href: '' } };
  return { ids, fields, document, window };
}

async function until(check, description, milliseconds=2500) {
  const end = Date.now() + milliseconds;
  while (Date.now() < end) {
    if (check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`timeout: ${description}`);
}

function load(page, script) {
  // A vm context is useful for deterministic DOM shims, NOT a secure execution boundary.
  const context = vm.createContext({
    document: page.document, window: page.window,
    fetch: (relativeURL, options) => fetch(new URL(relativeURL, baseURL), options),
    console: {log() {}, error() {}}, setTimeout, clearTimeout
  });
  vm.runInContext(script, context, { timeout: 2000, filename:'candidate-app.js' });
}

async function check() {
  assert(scriptPath && baseURL, 'expected candidate app.js path and base URL');
  const script = fs.readFileSync(scriptPath, 'utf8');
  const page = fakePage();
  load(page, script);
  const select = page.ids.get('project-select');
  await until(() => select.children.length >= 2, 'initial list options');
  assert.equal(select.children.length, 2, 'expected both projects in UI');
  assert(select.events.has('change'), 'missing project change listener');
  select.value = '1';
  await select.events.get('change')();
  assert.equal(page.ids.get('project-details').hidden, false, 'details were not shown');
  for (const [field, value] of Object.entries(EXPECTED)) {
    assert.equal(page.fields.get(field).textContent, value, `rendered field incorrect: ${field}`);
  }
  assert.equal(page.ids.get('export').disabled, true, 'export incorrectly enabled before save');
  page.ids.get('notes').value = 'DOM runtime verified';
  assert(page.ids.get('save').events.has('click'), 'missing save listener');
  await page.ids.get('save').events.get('click')();
  assert.equal(page.ids.get('export').disabled, false, 'export not enabled after save');
  const actual = await (await fetch(new URL('/api/projects/1',baseURL))).json();
  assert.equal(actual.notes, 'DOM runtime verified', 'save did not persist to real API');
  assert(page.ids.get('export').events.has('click'), 'missing export click listener');
  page.ids.get('export').events.get('click')();
  assert.equal(page.window.location.href, '/api/projects/1/export', 'export action URL incorrect');
  const reopened = fakePage();
  load(reopened, script);
  await until(() => reopened.ids.get('project-select').children.length >= 2, 'reload list');
  reopened.ids.get('project-select').value = '1';
  await reopened.ids.get('project-select').events.get('change')();
  assert.equal(reopened.ids.get('notes').value, 'DOM runtime verified', 'reload lost saved note');
  if (testMode === '--m1-error') {
    const failed = fakePage();
    load(failed, script);
    await until(() => failed.ids.get('project-select').children.length >= 2, 'failure page list');
    failed.ids.get('project-select').value = '999'; // 404 from real HTTP server
    await failed.ids.get('project-select').events.get('change')();
    assert.equal(failed.ids.get('project-details').hidden, true, 'failed detail remains visible');
    assert.equal(failed.ids.get('error').hidden, false, 'missing user-visible error alert');
    assert.match(failed.ids.get('error').textContent, /Load failed.*HTTP 404/);
  }
  process.stdout.write(JSON.stringify({status:'PASS',mode:'synthetic-dom-real-http',fields:Object.keys(EXPECTED).length})+'\n');
}
check().catch(error => {
  process.stdout.write(JSON.stringify({status:'FAIL',mode:'synthetic-dom-real-http',error:String(error.message||error).slice(0,500)})+'\n');
  process.exitCode=1;
});
