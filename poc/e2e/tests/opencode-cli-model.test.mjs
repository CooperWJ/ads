import assert from 'node:assert/strict';
import { access, chmod, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { opencodeCli } from '../opencode-cli-model.ts';

const DEFAULT_REPLY = JSON.stringify({
  tool_calls: [{ name: 'browser.click', input: { selector: '#save' } }],
});

const FAKE_CLI = "#!/usr/bin/env node\nimport fs from 'node:fs';\nimport path from 'node:path';\n\nconst args = process.argv.slice(2);\nconst logPath = process.env.ADS_E2E_OPENCODE_TEST_LOG;\nconst record = (value) => fs.appendFileSync(logPath, JSON.stringify(value) + '\\n');\nconst valueAfter = (flag) => {\n  const index = args.indexOf(flag);\n  return index >= 0 ? args[index + 1] : undefined;\n};\nconst defaultReply = JSON.stringify({\n  tool_calls: [{ name: 'browser.click', input: { selector: '#save' } }]\n});\n\nif (args[0] === 'run') {\n  const directory = valueAfter('--dir') ?? process.cwd();\n  const files = [];\n  for (let i = 0; i < args.length; i += 1) {\n    if (args[i] === '--file' && args[i + 1]) files.push(args[i + 1]);\n  }\n  const config = JSON.parse(fs.readFileSync(path.join(directory, 'opencode.json'), 'utf8'));\n  const agent = fs.readFileSync(path.join(directory, '.opencode/agents/ads-e2e-model.md'), 'utf8');\n  const attachments = files.map((file) => ({\n    path: file,\n    name: path.basename(file),\n    content: file.endsWith('.md') ? fs.readFileSync(file, 'utf8') : undefined,\n    bytes: fs.statSync(file).size\n  }));\n  record({ command: 'run', directory, cwd: process.cwd(), args, config, agent, attachments });\n  if (process.env.ADS_E2E_TEST_NO_SESSION !== '1') {\n    console.log(JSON.stringify({ type: 'step_start', sessionID: 'ses_fake' }));\n    console.log(JSON.stringify({ type: 'text', sessionID: 'ses_fake', part: {\n      text: process.env.ADS_E2E_TEST_REPLY ?? defaultReply\n    }}));\n    console.log(JSON.stringify({ type: 'step_finish', sessionID: 'ses_fake', part: {\n      reason: 'stop',\n      cost: 0.002,\n      tokens: { input: 100, output: 40, reasoning: 10, cache: { read: 20, write: 5 } }\n    }}));\n  }\n  process.exit(process.env.ADS_E2E_TEST_RUN_FAIL === '1' ? 1 : 0);\n}\n\nif (args[0] === 'session' && args[1] === 'export') {\n  record({ command: 'export', sessionID: args[2] });\n  if (process.env.ADS_E2E_TEST_EXPORT_FAIL === '1') {\n    process.stderr.write('PRIVATE EXPORT ERROR');\n    process.exit(1);\n  }\n  const reply = process.env.ADS_E2E_TEST_REPLY ?? defaultReply;\n  const data = {\n    messages: [{\n      info: {\n        type: 'assistant',\n        model: {\n          providerID: process.env.ADS_E2E_TEST_PROVIDER ?? 'opencode',\n          modelID: process.env.ADS_E2E_TEST_MODEL ?? 'deepseek-v4.1-flash-free'\n        },\n        tokens: { input: 100, output: 40, reasoning: 10, cache: { read: 20, write: 5 } },\n        cost: 0.002,\n        finish: 'stop'\n      },\n      parts: [{ type: 'text', text: reply }]\n    }]\n  };\n  process.stdout.write(JSON.stringify(data));\n  process.exit(0);\n}\n\nif (args[0] === 'session' && args[1] === 'delete') {\n  record({ command: 'delete', sessionID: args[2] });\n  process.exit(process.env.ADS_E2E_TEST_DELETE_FAIL === '1' ? 1 : 0);\n}\n\nprocess.stderr.write('UNKNOWN FAKE COMMAND');\nprocess.exit(2);\n";

async function setup() {
  const directory = await mkdtemp(join(tmpdir(), 'ads-e2e-opencode-cli-test-'));
  const binary = join(directory, 'fake-opencode.mjs');
  const log = join(directory, 'calls.jsonl');
  await writeFile(binary, FAKE_CLI, 'utf8');
  await chmod(binary, 0o755);
  await writeFile(log, '', 'utf8');
  const previous = {};
  const resetKeys = [
    'ADS_E2E_OPENCODE_BIN', 'ADS_E2E_OPENCODE_TEST_LOG', 'ADS_E2E_OPENCODE_CLI_MODEL',
    'ADS_E2E_TEST_REPLY', 'ADS_E2E_TEST_MODEL', 'ADS_E2E_TEST_PROVIDER',
    'ADS_E2E_TEST_EXPORT_FAIL', 'ADS_E2E_TEST_DELETE_FAIL',
    'ADS_E2E_TEST_NO_SESSION', 'ADS_E2E_TEST_RUN_FAIL',
  ];
  for (const key of resetKeys) {
    previous[key] = process.env[key];
    delete process.env[key];
  }
  Object.assign(process.env, {
    ADS_E2E_OPENCODE_BIN: binary,
    ADS_E2E_OPENCODE_TEST_LOG: log,
    ADS_E2E_OPENCODE_CLI_MODEL: 'opencode/deepseek-v4.1-flash-free',
    ADS_E2E_TEST_REPLY: DEFAULT_REPLY,
  });
  return {
    directory,
    log,
    async close() {
      for (const [key, value] of Object.entries(previous)) {
        if (value === undefined) delete process.env[key];
        else process.env[key] = value;
      }
      await rm(directory, { recursive: true, force: true });
    },
  };
}

async function records(log) {
  const text = await readFile(log, 'utf8');
  return text.trim() ? text.trim().split('\n').map((line) => JSON.parse(line)) : [];
}

function options(reply = DEFAULT_REPLY) {
  process.env.ADS_E2E_TEST_REPLY = reply;
  return {
    prompt: [
      { role: 'system', content: 'system instructions for the e2e agent' },
      { role: 'user', content: [
        { type: 'text', text: 'Click the save button in the visible UI.' },
        { type: 'image', data: { type: 'data', data: Buffer.from('png-fixture').toString('base64') }, mediaType: 'image/png' },
      ] },
    ],
    tools: [{
      type: 'function',
      name: 'browser.click',
      description: 'Click a visible browser element.',
      inputSchema: { type: 'object', properties: { selector: { type: 'string' } }, required: ['selector'] },
    }],
    toolChoice: { type: 'required' },
  };
}

test('OpenCode CLI adapter isolates tools, binds model identity, captures usage, and deletes the session', async () => {
  const env = await setup();
  try {
    const model = opencodeCli('opencode/deepseek-v4.1-flash-free');
    const result = await model.doGenerate(options());
    assert.equal(result.content.length, 1);
    assert.equal(result.content[0].type, 'tool-call');
    assert.equal(result.content[0].toolName, 'browser.click');
    assert.deepEqual(JSON.parse(result.content[0].input), { selector: '#save' });
    assert.equal(result.finishReason.unified, 'tool-calls');
    assert.equal(result.usage.inputTokens.total, 125);
    assert.equal(result.usage.inputTokens.noCache, 100);
    assert.equal(result.usage.inputTokens.cacheRead, 20);
    assert.equal(result.usage.inputTokens.cacheWrite, 5);
    assert.equal(result.usage.outputTokens.total, 40);
    assert.equal(result.usage.outputTokens.text, 30);
    assert.equal(result.usage.outputTokens.reasoning, 10);
    const metadata = result.providerMetadata['opencode-cli'];
    assert.equal(metadata.providerId, 'opencode');
    assert.equal(metadata.modelId, 'deepseek-v4.1-flash-free');
    assert.equal(metadata.costUsd, 0.002);
    assert.equal(metadata.sessionDeleted, true);
    assert.match(metadata.sessionDigest, /^[a-f0-9]{64}$/);

    const calls = await records(env.log);
    const run = calls.find((call) => call.command === 'run');
    assert.ok(run);
    assert.equal(Object.keys(run.config.mcp).length, 0);
    assert.deepEqual(run.config.plugins, []);
    assert.ok(run.config.policies.some((rule) =>
      rule.action === 'tool.use' && rule.resource === '*' && rule.effect === 'deny'));
    assert.ok(run.config.experimental.policies.some((rule) =>
      rule.action === 'provider.use' && rule.resource === '*' && rule.effect === 'deny'));
    assert.ok(run.config.experimental.policies.some((rule) =>
      rule.action === 'provider.use' && rule.resource === 'opencode' && rule.effect === 'allow'));
    assert.match(run.agent, /steps: 1/);
    assert.match(run.agent, /action: "\*"/);
    assert.match(run.agent, /system instructions for the e2e agent/);
    assert.ok(run.attachments.some((file) => file.name === 'e2e-conversation.md'
      && file.content.includes('Click the save button')));
    assert.ok(run.attachments.some((file) => file.name === 'image-001.png' && file.bytes > 0));
    assert.ok(run.args.includes('opencode/deepseek-v4.1-flash-free'));
    assert.ok(run.args.includes('ads-e2e-model'));
    assert.equal(calls.filter((call) => call.command === 'export').length, 1);
    assert.equal(calls.filter((call) => call.command === 'delete').length, 1);
    await assert.rejects(access(run.directory));
  } finally {
    await env.close();
  }
});

test('model identity mismatch fails closed and still deletes the OpenCode session', async () => {
  const env = await setup();
  try {
    process.env.ADS_E2E_TEST_MODEL = 'unexpected-model';
    const model = opencodeCli('opencode/deepseek-v4.1-flash-free');
    await assert.rejects(model.doGenerate(options()), /model identity did not match/);
    const calls = await records(env.log);
    assert.equal(calls.filter((call) => call.command === 'delete').length, 1);
  } finally {
    await env.close();
  }
});

test('session export failure fails closed and still attempts cleanup', async () => {
  const env = await setup();
  try {
    process.env.ADS_E2E_TEST_EXPORT_FAIL = '1';
    const model = opencodeCli('opencode/deepseek-v4.1-flash-free');
    await assert.rejects(model.doGenerate(options()), /session export failed/);
    const calls = await records(env.log);
    assert.equal(calls.filter((call) => call.command === 'delete').length, 1);
  } finally {
    await env.close();
  }
});

test('missing session id is rejected and no unbound session is accepted', async () => {
  const env = await setup();
  try {
    process.env.ADS_E2E_TEST_NO_SESSION = '1';
    const model = opencodeCli('opencode/deepseek-v4.1-flash-free');
    await assert.rejects(model.doGenerate(options()), /did not report a session id/);
    const calls = await records(env.log);
    assert.equal(calls.filter((call) => call.command === 'delete').length, 0);
  } finally {
    await env.close();
  }
});

test('unsupported tool names never become e2e tool calls', async () => {
  const env = await setup();
  try {
    const reply = JSON.stringify({ tool_calls: [{ name: 'shell.run', input: { command: 'rm -rf .' } }] });
    const model = opencodeCli('opencode/deepseek-v4.1-flash-free');
    const result = await model.doGenerate(options(reply));
    assert.equal(result.content[0].type, 'text');
    assert.match(result.content[0].text, /unsupported tool call/);
  } finally {
    await env.close();
  }
});

test('OpenCode CLI nonzero exit is not accepted even if a session was created', async () => {
  const env = await setup();
  try {
    process.env.ADS_E2E_TEST_RUN_FAIL = '1';
    const model = opencodeCli('opencode/deepseek-v4.1-flash-free');
    await assert.rejects(model.doGenerate(options()), /did not complete successfully/);
    const calls = await records(env.log);
    assert.equal(calls.filter((call) => call.command === 'delete').length, 1);
  } finally {
    await env.close();
  }
});
