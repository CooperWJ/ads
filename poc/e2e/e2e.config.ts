import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';

// 连接一次性虚构应用；不调用模型，不读取候选的测试预期。
export default {
  targets: [{ name: 'chromium', engine: web(), app: { url: process.env.ADS_E2E_URL! } }],
  tests: ['tests/journey.e2e.ts'],
  retries: 0,
  workers: 1,
  timeout: 30000,
  actionTimeout: 5000,
  assertionTimeout: 5000,
  cache: 'off',
  trace: 'on',
  reporters: ['list', 'junit', 'markdown'],
} satisfies E2EConfig;
