export type AgentVerification = {
  ok: boolean;
  code?: string;
  [key: string]: unknown;
};

export type BoundedAgentRepairOptions = {
  initialPrompt: string;
  act: (prompt: string) => Promise<unknown>;
  verify: () => Promise<AgentVerification> | AgentVerification;
  buildRepairPrompt: (observation: AgentVerification, repairNumber: number) => string;
  maxRepairs?: number;
};

export type BoundedAgentRepairResult = {
  repairAttempts: number;
  observations: AgentVerification[];
};

/**
 * Run an Agent action, verify it deterministically, and allow only a small,
 * explicit repair budget. Oracle errors and Agent action errors are propagated;
 * only a structured { ok: false } verification result can trigger a repair.
 */
export async function runWithBoundedRepair(
  options: BoundedAgentRepairOptions,
): Promise<BoundedAgentRepairResult> {
  const maxRepairs = options.maxRepairs ?? 1;
  if (!Number.isInteger(maxRepairs) || maxRepairs < 0 || maxRepairs > 2) {
    throw new Error('maxRepairs must be an integer between 0 and 2.');
  }
  if (typeof options.initialPrompt !== 'string' || !options.initialPrompt.trim()) {
    throw new Error('initialPrompt must be a non-empty string.');
  }
  if (typeof options.act !== 'function' || typeof options.verify !== 'function'
      || typeof options.buildRepairPrompt !== 'function') {
    throw new Error('act, verify, and buildRepairPrompt callbacks are required.');
  }

  const observations: AgentVerification[] = [];
  await options.act(options.initialPrompt);
  let observation = await options.verify();
  if (!observation || typeof observation.ok !== 'boolean') {
    throw new Error('deterministic verifier must return an object with boolean ok.');
  }
  observations.push(observation);

  let repairAttempts = 0;
  while (!observation.ok && repairAttempts < maxRepairs) {
    repairAttempts += 1;
    const prompt = options.buildRepairPrompt(observation, repairAttempts);
    if (typeof prompt !== 'string' || !prompt.trim()) {
      throw new Error('repair prompt builder must return a non-empty string.');
    }
    await options.act(prompt);
    observation = await options.verify();
    if (!observation || typeof observation.ok !== 'boolean') {
      throw new Error('deterministic verifier must return an object with boolean ok.');
    }
    observations.push(observation);
  }

  if (!observation.ok) {
    const error = new Error(`Agent repair budget exhausted after ${repairAttempts} repair attempt(s).`);
    Object.assign(error, {
      code: 'AGENT_REPAIR_EXHAUSTED',
      repairAttempts,
      lastObservation: observation,
    });
    throw error;
  }

  return { repairAttempts, observations };
}
