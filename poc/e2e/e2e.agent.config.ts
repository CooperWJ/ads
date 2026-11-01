import type { E2EConfig } from 'e2e';
import { opencodeConsole } from 'e2e/oauth/opencode-console';
import base from './e2e.config.ts';

const modelId = process.env.ADS_E2E_OPENCODE_MODEL?.trim();
if (!modelId) {
  throw new Error(
    'ADS_E2E_OPENCODE_MODEL is required; list eligible models with "npm run models:agent". No model fallback is permitted.',
  );
}

if (!/^(?:go\/)?[A-Za-z0-9._:/@+-]{1,128}$/.test(modelId)) {
  throw new Error('ADS_E2E_OPENCODE_MODEL must be an exact OpenCode Console model id.');
}

export default {
  ...base,
  tests: ['tests/agent-journey.e2e.ts'],
  timeout: 90000,
  agents: {
    default: {
      model: opencodeConsole(modelId),
      maxSteps: 8,
      maxModelCalls: 12,
      maxInputTokens: 32000,
      context: [
        'Operate only through the visible application UI.',
        'Do not use APIs, databases, shell commands, or external tools.',
        'Perform only the requested note edit and save. Do not export or modify other projects.',
        'The test performs independent deterministic UI, persistence, API, and XLSX assertions after your action.',
      ].join(' '),
    },
  },
} satisfies E2EConfig;
