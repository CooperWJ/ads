import { test } from '@e2e-dev/web';
import { expect } from 'e2e';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import { runWithBoundedRepair } from '../agent-repair.ts';

const EXPECTED_NOTE = 'Reviewed in M0';

function persistedNote(): string {
  const script = [
    'import os, sqlite3',
    "db = sqlite3.connect(os.environ['ADS_DB_PATH'])",
    "row = db.execute('SELECT notes FROM projects WHERE id=1').fetchone()",
    "print(row[0] if row else '')",
  ].join('; ');
  return execFileSync(process.env.ADS_PYTHON!, ['-c', script], {
    encoding: 'utf8',
    env: process.env,
  }).trim();
}

function saveAttempts(): number {
  const counter = join(dirname(process.env.ADS_DB_PATH!), '.ads-e2e-save-attempts');
  try {
    return Number(readFileSync(counter, 'utf8').trim());
  } catch {
    return 0;
  }
}

// The model performs the UI actions. A deterministic DB/UI oracle decides whether
// repair is needed; the model's own success narration is never accepted as proof.
test('agent-bounded-repair-save-refresh-export', async ({ app, agent, screen, browser }) => {
  if (process.env.ADS_E2E_FAIL_FIRST_SAVE !== '1') {
    throw new Error('bounded repair journey requires the one-shot transient-save fixture');
  }

  await app.open('/');
  await expect(screen.getByRole('option', 'Project Echo')).toBeAttached();

  let verificationNumber = 0;
  const result = await runWithBoundedRepair({
    initialPrompt:
      'In the visible UI, select Project Echo, enter exactly "Reviewed in M0" in Editable notes, and click Save notes exactly once. Do not retry if it fails. Do not export. Stop after this one save attempt.',
    act: (prompt) => agent.act(prompt),
    verify: async () => {
      verificationNumber += 1;
      const status = (await screen.getByRole('status').textContent())?.trim() ?? '';
      const note = await screen.getByLabel('Editable notes').inputValue();
      const persisted = persistedNote();
      const attempts = saveAttempts();

      if (verificationNumber === 1) {
        expect(status).toBe('Save failed: HTTP 503');
        expect(note).toBe(EXPECTED_NOTE);
        expect(persisted).toBe('');
        expect(attempts).toBe(1);
        await app.screenshot('agent-first-save-rejected');
        return { ok: false, code: 'SAVE_HTTP_503', status, note, persisted, attempts };
      }

      expect(status).toBe('Saved');
      expect(note).toBe(EXPECTED_NOTE);
      expect(persisted).toBe(EXPECTED_NOTE);
      expect(attempts).toBe(2);
      await app.screenshot('agent-repair-save-verified');
      return { ok: true, code: 'SAVE_VERIFIED', status, note, persisted, attempts };
    },
    buildRepairPrompt: (observation, repairNumber) =>
      [
        `The independent deterministic verifier reports repair ${repairNumber} is required.`,
        `Observed code: ${observation.code}; UI status: ${observation.status}; database note: ${JSON.stringify(observation.persisted)}; save requests: ${observation.attempts}.`,
        'The first Save notes request was rejected with HTTP 503 and the database remains unchanged.',
        'Project Echo is still selected and Editable notes must remain exactly "Reviewed in M0". Click Save notes exactly once more. Do not change another field or project. Do not export. Stop after the retry.',
      ].join(' '),
    maxRepairs: 1,
  });

  expect(result.repairAttempts).toBe(1);
  expect(result.observations.map((item) => item.code)).toEqual(['SAVE_HTTP_503', 'SAVE_VERIFIED']);

  // Re-read persisted state after a full browser reload; the third save only enables export.
  await browser.reload();
  await screen.getByLabel('Select project').selectOption({ label: 'Project Echo' });
  await expect(screen.getByLabel('Editable notes')).toHaveValue(EXPECTED_NOTE);
  await screen.getByRole('button', 'Save notes').tap();
  await expect(screen.getByRole('status')).toHaveText('Saved');
  await expect(screen.getByRole('button', 'Export XLSX')).toBeEnabled();
  expect(saveAttempts()).toBe(3);

  const download = await browser.waitForDownload(() => screen.getByRole('button', 'Export XLSX').tap());

  // Independent oracle reads the actual DB and downloaded workbook, not Agent narration.
  const observed = JSON.parse(execFileSync(process.env.ADS_PYTHON!, [
    'assert_product.py', process.env.ADS_DB_PATH!, download.absolutePath,
  ], { encoding: 'utf8' }));
  expect(observed.persisted).toBe(EXPECTED_NOTE);
  expect(observed.exported).toBe(EXPECTED_NOTE);
  await app.screenshot('agent-repaired-saved-refreshed-exported');
});
