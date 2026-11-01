import { test } from '@e2e-dev/web';
import { expect } from 'e2e';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
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

function exportAttempts(): number {
  const counter = join(dirname(process.env.ADS_DB_PATH!), '.ads-e2e-export-attempts');
  try {
    return Number(readFileSync(counter, 'utf8').trim());
  } catch {
    return 0;
  }
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
      const statusLocator = screen.getByRole('status');
      await expect(statusLocator).toHaveText(verificationNumber === 1 ? 'Save failed: HTTP 503' : 'Saved');
      const status = (await statusLocator.textContent())?.trim() ?? '';
      const selectedProjectId = await screen.getByLabel('Select project').inputValue();
      const note = await screen.getByLabel('Editable notes').inputValue();
      const persisted = persistedNote();
      const attempts = saveAttempts();

      if (verificationNumber === 1) {
        expect(status).toBe('Save failed: HTTP 503');
        expect(attempts).toBe(1);
        expect(exportAttempts()).toBe(0);
        await app.screenshot('agent-first-save-rejected');
        return {
          ok: selectedProjectId === '1' && note === EXPECTED_NOTE && persisted === '',
          code: 'SAVE_HTTP_503', status, selectedProjectId, note, persisted, attempts,
        };
      }

      expect(status).toBe('Saved');
      expect(selectedProjectId).toBe('1');
      expect(note).toBe(EXPECTED_NOTE);
      expect(persisted).toBe(EXPECTED_NOTE);
      expect(attempts).toBe(2);
      expect(exportAttempts()).toBe(0);
      await app.screenshot('agent-repair-save-verified');
      return { ok: true, code: 'SAVE_VERIFIED', status, note, persisted, attempts };
    },
    buildRepairPrompt: (observation, repairNumber) =>
      [
        `The independent deterministic verifier reports repair ${repairNumber} is required.`,
        `Observed code: ${String(observation.code)}; UI status: ${String(observation.status)}; selected project id: ${String(observation.selectedProjectId)}; note: ${JSON.stringify(observation.note)}; database note: ${JSON.stringify(observation.persisted)}; save requests: ${String(observation.attempts)}.`,
        'The first Save notes request was rejected with HTTP 503 and the database remains unchanged.',
        'Select Project Echo (id 1) if needed, keep Editable notes exactly "Reviewed in M0", then click Save notes exactly once more. Do not change another field. Do not export. Stop after the retry.',
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
  expect(exportAttempts()).toBe(1);

  // Independent oracle reads the actual DB and downloaded workbook, not Agent narration.
  const observed = JSON.parse(execFileSync(process.env.ADS_PYTHON!, [
    'assert_product.py', process.env.ADS_DB_PATH!, download.absolutePath,
  ], { encoding: 'utf8' }));
  expect(observed.persisted).toBe(EXPECTED_NOTE);
  expect(observed.exported).toBe(EXPECTED_NOTE);
  await app.screenshot('agent-repaired-saved-refreshed-exported');

  const ledgerPath = process.env.ADS_E2E_REPAIR_LEDGER_PATH;
  if (!ledgerPath) throw new Error('ADS_E2E_REPAIR_LEDGER_PATH is required for repair evidence.');
  writeFileSync(ledgerPath, JSON.stringify({
    schema: 'ads-agent-repair-ledger/v1',
    test_id: 'agent-bounded-repair-save-refresh-export',
    max_repairs: 1,
    repair_attempts: result.repairAttempts,
    observations: result.observations,
    save_attempts: saveAttempts(),
    export_attempts: exportAttempts(),
    final_persisted: observed.persisted,
    final_exported: observed.exported,
  }, null, 2));
});
