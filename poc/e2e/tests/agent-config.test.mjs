import assert from 'node:assert/strict';
import test from 'node:test';

test('agent profile uses an explicit OpenCode Console model and disables e2e replay', async () => {
  process.env.ADS_E2E_OPENCODE_MODEL = 'go/deepseek-v4.1-flash';
  const { default: config } = await import('../e2e.agent.config.ts');
  assert.equal(config.cache, 'off');
  assert.deepEqual(config.tests, ['tests/agent-journey.e2e.ts']);
  assert.equal(config.agents.default.model.provider, 'opencode.go');
  assert.equal(config.agents.default.model.modelId, 'deepseek-v4.1-flash');
  assert.equal(config.agents.default.maxSteps, 8);
  assert.equal(config.agents.default.maxModelCalls, 12);
});

test('OpenCode CLI profile uses the exact configured provider/model without a fallback', async () => {
  process.env.ADS_E2E_OPENCODE_CLI_MODEL = 'opencode/deepseek-v4.1-flash-free';
  const { default: config } = await import('../e2e.agent.opencode-cli.config.ts');
  assert.equal(config.cache, 'off');
  assert.deepEqual(config.tests, ['tests/agent-journey.e2e.ts']);
  assert.equal(config.agents.default.model.provider, 'opencode-cli');
  assert.equal(config.agents.default.model.modelId, 'opencode/deepseek-v4.1-flash-free');
  assert.equal(config.agents.default.maxSteps, 8);
  assert.equal(config.agents.default.maxModelCalls, 12);
});
