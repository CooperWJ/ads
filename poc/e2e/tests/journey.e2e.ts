import { test } from '@e2e-dev/web';
import { expect } from 'e2e';
import { execFileSync } from 'node:child_process';

test('save-refresh-export', async ({ app, screen, browser }) => {
  await app.open('/');
  await expect(screen.getByRole('option', 'Project Echo')).toBeAttached();
  await screen.getByLabel('Select project').selectOption({ label: 'Project Echo' });
  await expect(screen.getByRole('region', 'Project details')).toBeVisible();
  await expect(screen.getByRole('button', 'Export XLSX')).toBeDisabled();
  await screen.getByLabel('Editable notes').fill('Reviewed in M0');
  await screen.getByRole('button', 'Save notes').tap();
  await expect(screen.getByRole('status')).toHaveText('Saved');
  await browser.reload();
  await screen.getByLabel('Select project').selectOption({ label: 'Project Echo' });
  await expect(screen.getByLabel('Editable notes')).toHaveValue('Reviewed in M0');
  await screen.getByRole('button', 'Save notes').tap();
  await expect(screen.getByRole('button', 'Export XLSX')).toBeEnabled();
  const download = await browser.waitForDownload(() => screen.getByRole('button', 'Export XLSX').tap());
  // 验收程序仅解析 DB/下载数据，不运行候选实现；预期来自冻结虚构契约。
  const observed = JSON.parse(execFileSync(process.env.ADS_PYTHON!, [
    'assert_product.py', process.env.ADS_DB_PATH!, download.absolutePath,
  ], { encoding: 'utf8' }));
  expect(observed.persisted).toBe('Reviewed in M0');
  expect(observed.exported).toBe('Reviewed in M0');
  await app.screenshot('saved-refreshed-exported');
});
