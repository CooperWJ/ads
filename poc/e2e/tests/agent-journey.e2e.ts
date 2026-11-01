import { test } from '@e2e-dev/web';
import { expect } from 'e2e';
import { execFileSync } from 'node:child_process';

// This profile is deliberately separate from the deterministic CI baseline.
// The Agent performs only the initial UI action; all success claims are asserted below.
test('agent-save-refresh-export', async ({ app, agent, screen, browser }) => {
  await app.open('/');
  await expect(screen.getByRole('option', 'Project Echo')).toBeAttached();

  await agent.act(
    'In the visible UI, select Project Echo, enter exactly "Reviewed in M0" in Editable notes, and click Save notes. Do not export. Do not change any other project. Stop after saving.',
  );

  // Deterministic assertions follow the Agent action in this same test.
  await expect(screen.getByRole('status')).toHaveText('Saved');
  await expect(screen.getByLabel('Editable notes')).toHaveValue('Reviewed in M0');

  await browser.reload();
  await screen.getByLabel('Select project').selectOption({ label: 'Project Echo' });
  await expect(screen.getByLabel('Editable notes')).toHaveValue('Reviewed in M0');

  await screen.getByRole('button', 'Save notes').tap();
  await expect(screen.getByRole('button', 'Export XLSX')).toBeEnabled();
  const download = await browser.waitForDownload(() => screen.getByRole('button', 'Export XLSX').tap());

  // Independent oracle reads the actual DB and downloaded workbook, not Agent narration.
  const observed = JSON.parse(execFileSync(process.env.ADS_PYTHON!, [
    'assert_product.py', process.env.ADS_DB_PATH!, download.absolutePath,
  ], { encoding: 'utf8' }));
  expect(observed.persisted).toBe('Reviewed in M0');
  expect(observed.exported).toBe('Reviewed in M0');
  await app.screenshot('agent-saved-refreshed-exported');
});
