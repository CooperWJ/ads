import assert from 'node:assert/strict';
import test from 'node:test';

import { runWithBoundedRepair } from '../agent-repair.ts';

test('successful first action does not consume repair budget', async () => {
  const actions = [];
  let verifications = 0;
  const result = await runWithBoundedRepair({
    initialPrompt: 'complete the task',
    act: async (prompt) => actions.push(prompt),
    verify: async () => {
      verifications += 1;
      return { ok: true, code: 'VERIFIED' };
    },
    buildRepairPrompt: () => 'repair',
    maxRepairs: 1,
  });
  assert.deepEqual(actions, ['complete the task']);
  assert.equal(verifications, 1);
  assert.equal(result.repairAttempts, 0);
  assert.equal(result.observations.length, 1);
});

test('one deterministic failure triggers exactly one bounded repair and re-verification', async () => {
  const actions = [];
  let verifications = 0;
  const result = await runWithBoundedRepair({
    initialPrompt: 'attempt once',
    act: async (prompt) => actions.push(prompt),
    verify: async () => {
      verifications += 1;
      return verifications === 1
        ? { ok: false, code: 'SAVE_HTTP_503', persisted: '' }
        : { ok: true, code: 'VERIFIED', persisted: 'expected value' };
    },
    buildRepairPrompt: (observation, repairNumber) =>
      `repair ${repairNumber}: ${observation.code}; persisted=${observation.persisted}`,
    maxRepairs: 1,
  });
  assert.deepEqual(actions, [
    'attempt once',
    'repair 1: SAVE_HTTP_503; persisted=',
  ]);
  assert.equal(verifications, 2);
  assert.equal(result.repairAttempts, 1);
  assert.deepEqual(result.observations.map((item) => item.ok), [false, true]);
});

test('repair budget exhaustion fails closed without a second repair', async () => {
  const actions = [];
  let verifications = 0;
  await assert.rejects(
    runWithBoundedRepair({
      initialPrompt: 'attempt once',
      act: async (prompt) => actions.push(prompt),
      verify: async () => {
        verifications += 1;
        return { ok: false, code: 'STILL_NOT_PERSISTED' };
      },
      buildRepairPrompt: (_observation, repairNumber) => `repair ${repairNumber}`,
      maxRepairs: 1,
    }),
    (error) => {
      assert.equal(error.code, 'AGENT_REPAIR_EXHAUSTED');
      assert.equal(error.repairAttempts, 1);
      assert.equal(error.lastObservation.code, 'STILL_NOT_PERSISTED');
      return true;
    },
  );
  assert.deepEqual(actions, ['attempt once', 'repair 1']);
  assert.equal(verifications, 2);
});

test('zero repair budget verifies once and never retries', async () => {
  const actions = [];
  await assert.rejects(
    runWithBoundedRepair({
      initialPrompt: 'attempt once',
      act: async (prompt) => actions.push(prompt),
      verify: async () => ({ ok: false, code: 'FAILED' }),
      buildRepairPrompt: () => 'must not run',
      maxRepairs: 0,
    }),
    /budget exhausted after 0 repair attempt/,
  );
  assert.deepEqual(actions, ['attempt once']);
});

test('invalid repair budgets and invalid verifier output are rejected', async () => {
  await assert.rejects(
    runWithBoundedRepair({
      initialPrompt: 'attempt',
      act: async () => {},
      verify: async () => ({ ok: true }),
      buildRepairPrompt: () => 'repair',
      maxRepairs: 3,
    }),
    /between 0 and 2/,
  );
  await assert.rejects(
    runWithBoundedRepair({
      initialPrompt: 'attempt',
      act: async () => {},
      verify: async () => null,
      buildRepairPrompt: () => 'repair',
    }),
    /boolean ok/,
  );
});

test('Agent action errors and verifier exceptions are not silently retried', async () => {
  let actions = 0;
  await assert.rejects(
    runWithBoundedRepair({
      initialPrompt: 'attempt',
      act: async () => { actions += 1; throw new Error('agent transport failed'); },
      verify: async () => ({ ok: false }),
      buildRepairPrompt: () => 'repair',
    }),
    /agent transport failed/,
  );
  assert.equal(actions, 1);

  actions = 0;
  await assert.rejects(
    runWithBoundedRepair({
      initialPrompt: 'attempt',
      act: async () => { actions += 1; },
      verify: async () => { throw new Error('oracle unavailable'); },
      buildRepairPrompt: () => 'repair',
    }),
    /oracle unavailable/,
  );
  assert.equal(actions, 1);
});
