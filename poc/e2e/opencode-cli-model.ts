import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join } from 'node:path';

import type {
  LanguageModelV4,
  LanguageModelV4CallOptions,
  LanguageModelV4Content,
  LanguageModelV4FunctionTool,
  LanguageModelV4GenerateResult,
  LanguageModelV4Prompt,
} from '@ai-sdk/provider';

type Captured = {
  stdout: string;
  stderr: string;
  code: number | null;
  signal: NodeJS.Signals | null;
  error?: Error;
};

type JsonRecord = Record<string, unknown>;

type TranscriptFile = {
  path: string;
  label: string;
};

const IMAGE_EXTENSIONS: Record<string, string> = {
  'image/png': '.png',
  'image/jpeg': '.jpg',
  'image/webp': '.webp',
  'image/gif': '.gif',
};

function modelParts(modelId: string): { providerId: string; modelId: string } {
  const slash = modelId.indexOf('/');
  if (slash <= 0 || slash === modelId.length - 1) {
    throw new Error('ADS_E2E_OPENCODE_CLI_MODEL must be an exact provider/model id.');
  }
  return { providerId: modelId.slice(0, slash), modelId: modelId.slice(slash + 1) };
}

export function opencodeCli(modelId: string): LanguageModelV4 {
  modelParts(modelId);
  return {
    specificationVersion: 'v4',
    provider: 'opencode-cli',
    modelId,
    supportedUrls: {},
    doGenerate: (options) => generate(modelId, options),
    doStream: () => Promise.reject(new Error('opencode-cli returns complete responses; streaming is not supported')),
  };
}

function functionTools(options: LanguageModelV4CallOptions): LanguageModelV4FunctionTool[] {
  return (options.tools ?? []).filter((tool): tool is LanguageModelV4FunctionTool => tool.type === 'function');
}

function callsSchema(options: LanguageModelV4CallOptions): JsonRecord {
  const choice = options.toolChoice ?? { type: 'auto' };
  const names = choice.type === 'tool' ? [choice.toolName] : functionTools(options).map((tool) => tool.name);
  return {
    type: 'object',
    properties: {
      tool_calls: {
        type: 'array',
        minItems: choice.type === 'auto' ? 0 : 1,
        items: {
          type: 'object',
          properties: {
            name: { type: 'string', enum: names },
            input: { type: 'object' },
          },
          required: ['name', 'input'],
          additionalProperties: false,
        },
      },
      ...(choice.type === 'auto' ? { text: { type: 'string' } } : {}),
    },
    required: ['tool_calls'],
    additionalProperties: false,
  };
}

function replyRules(options: LanguageModelV4CallOptions): string {
  const tools = functionTools(options);
  const choice = options.toolChoice ?? { type: 'auto' };
  if (tools.length === 0 || choice.type === 'none') {
    return options.responseFormat?.type === 'json'
      ? 'Return exactly one JSON object and no prose or code fence.'
      : 'Answer with plain text. Do not call or invent tools.';
  }
  const must = choice.type === 'tool'
    ? `You must call exactly the tool "${choice.toolName}".`
    : choice.type === 'required'
      ? 'You must call at least one tool.'
      : 'Call a tool, or answer in words with {"tool_calls":[],"text":"..."} when no tool applies.';
  return [
    '# e2e response contract',
    'You are a model-only decision engine. You cannot operate the browser yourself.',
    'The e2e runner executes the tool calls you return and supplies the results in later messages.',
    'Return one JSON object only, without markdown fences:',
    '{"tool_calls":[{"name":"<exact tool name>","input":{}}]}',
    must,
    'Never invent tool names or arguments. Use only the tools and schemas below.',
    '# Allowed tools',
    JSON.stringify(tools.map((tool) => ({
      name: tool.name,
      description: tool.description,
      input_schema: tool.inputSchema,
    }))),
    '# JSON schema',
    JSON.stringify(callsSchema(options)),
  ].join('\n');
}

function imageBytes(data: Uint8Array | string): Buffer {
  return typeof data === 'string' ? Buffer.from(data, 'base64') : Buffer.from(data);
}

async function writeTranscript(
  prompt: LanguageModelV4Prompt,
  directory: string,
): Promise<{ system: string; transcriptPath: string; attachments: TranscriptFile[] }> {
  const system: string[] = [];
  const lines: string[] = [];
  const attachments: TranscriptFile[] = [];
  let imageIndex = 0;

  const appendImage = async (data: { type: string; data?: Uint8Array | string }, mediaType: string) => {
    if (data.type !== 'data' || data.data === undefined || !IMAGE_EXTENSIONS[mediaType]) {
      lines.push(`[Attachment omitted: unsupported non-image media type ${mediaType}]`);
      return;
    }
    imageIndex += 1;
    const filename = `image-${String(imageIndex).padStart(3, '0')}${IMAGE_EXTENSIONS[mediaType]}`;
    const path = join(directory, filename);
    await writeFile(path, imageBytes(data.data));
    attachments.push({ path, label: filename });
    lines.push(`[Image attached: ${filename} (${mediaType})]`);
  };

  for (const message of prompt) {
    if (message.role === 'system') {
      system.push(message.content);
      continue;
    }
    if (message.role === 'user') {
      lines.push('[USER]');
      for (const part of message.content) {
        if (part.type === 'text') lines.push(part.text);
        else await appendImage(part.data, part.mediaType);
      }
      continue;
    }
    if (message.role === 'assistant') {
      const calls = message.content.flatMap((part) =>
        part.type === 'tool-call'
          ? [{ id: part.toolCallId, name: part.toolName, input: part.input }]
          : [],
      );
      const words = message.content.flatMap((part) => part.type === 'text' ? [part.text] : []).join('\n');
      lines.push('[ASSISTANT]');
      lines.push(calls.length > 0 ? JSON.stringify({ tool_calls: calls }) : words);
      continue;
    }
    for (const part of message.content) {
      if (part.type !== 'tool-result') continue;
      lines.push(`[TOOL RESULT: ${part.toolName} ${part.toolCallId}]`);
      const output = part.output;
      if (output.type === 'text' || output.type === 'error-text') lines.push(output.value);
      else if (output.type === 'json' || output.type === 'error-json') lines.push(JSON.stringify(output.value));
      else if (output.type === 'execution-denied') lines.push(`denied: ${output.reason ?? 'no reason supplied'}`);
      else {
        for (const piece of output.value) {
          if (piece.type === 'text') lines.push(piece.text);
          else if (piece.type === 'file') await appendImage(piece.data, piece.mediaType);
        }
      }
    }
  }

  const transcriptPath = join(directory, 'e2e-conversation.md');
  await writeFile(transcriptPath, lines.join('\n\n'), 'utf8');
  return { system: system.join('\n\n'), transcriptPath, attachments };
}

async function capture(
  binary: string,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv,
  signal?: AbortSignal,
): Promise<Captured> {
  return await new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    let spawnError: Error | undefined;
    let child;
    try {
      child = spawn(binary, args, { cwd, env, signal, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (error) {
      resolve({ stdout, stderr, code: null, signal: null, error: error as Error });
      return;
    }
    child.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });
    child.on('error', (error) => { spawnError = error; });
    child.on('close', (code, closeSignal) => {
      resolve({ stdout, stderr, code, signal: closeSignal, error: spawnError });
    });
  });
}

function jsonLines(stdout: string): JsonRecord[] {
  return stdout.split('\n').flatMap((line) => {
    const value = line.trim();
    if (!value.startsWith('{')) return [];
    try {
      const parsed: unknown = JSON.parse(value);
      return typeof parsed === 'object' && parsed !== null ? [parsed as JsonRecord] : [];
    } catch {
      return [];
    }
  });
}

function sessionIdFrom(events: JsonRecord[]): string | undefined {
  for (const event of events) {
    const value = event.sessionID ?? event.sessionId
      ?? (typeof event.properties === 'object' && event.properties !== null
        ? (event.properties as JsonRecord).sessionID
        : undefined);
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return undefined;
}

function parseJsonOutput(stdout: string): JsonRecord {
  try {
    const value: unknown = JSON.parse(stdout);
    if (typeof value === 'object' && value !== null) return value as JsonRecord;
  } catch {
    // Some CLI versions add a non-JSON diagnostic line; try the JSON object span.
  }
  const start = stdout.indexOf('{');
  for (let end = stdout.lastIndexOf('}'); start >= 0 && end > start; end = stdout.lastIndexOf('}', end - 1)) {
    try {
      const value: unknown = JSON.parse(stdout.slice(start, end + 1));
      if (typeof value === 'object' && value !== null) return value as JsonRecord;
    } catch {
      // Try a shorter JSON span.
    }
  }
  throw new Error('OpenCode session export did not contain valid JSON.');
}

function assistantResult(
  exported: JsonRecord,
  stepFinish: JsonRecord | undefined,
  expectedProvider: string,
  expectedModel: string,
): {
  text: string;
  tokens: JsonRecord;
  cost?: number;
  finish?: string;
  providerId: string;
  modelId: string;
} {
  const messages = Array.isArray(exported.messages) ? exported.messages as JsonRecord[] : [];
  const assistants = messages.filter((message) => {
    const info = (message.info && typeof message.info === 'object' ? message.info : message) as JsonRecord;
    return info.type === 'assistant' || info.role === 'assistant';
  });
  if (assistants.length !== 1) {
    throw new Error('OpenCode session must contain exactly one assistant model response.');
  }

  const message = assistants[0];
  const info = (message.info && typeof message.info === 'object' ? message.info : message) as JsonRecord;
  const parts = Array.isArray(message.parts) ? message.parts as JsonRecord[]
    : Array.isArray(info.content) ? info.content as JsonRecord[] : [];
  const text = parts.filter((part) => part.type === 'text' && typeof part.text === 'string')
    .map((part) => part.text as string).join('\n');
  if (!text.trim()) throw new Error('OpenCode session did not contain assistant text.');
  if (parts.some((part) => ['tool', 'tool-call', 'tool_use', 'tool-result'].includes(String(part.type)))) {
    throw new Error('OpenCode native tool execution is forbidden in the e2e model adapter.');
  }

  const model = (info.model && typeof info.model === 'object' ? info.model
    : exported.info && typeof exported.info === 'object' ? (exported.info as JsonRecord).model : undefined) as JsonRecord | undefined;
  const providerId = String(model?.providerID ?? model?.providerId ?? info.providerID ?? '');
  const modelId = String(model?.modelID ?? model?.modelId ?? info.modelID ?? '');
  if (providerId !== expectedProvider || modelId !== expectedModel) {
    throw new Error('OpenCode session model identity did not match the explicitly requested provider/model.');
  }

  const finishPart = stepFinish?.part && typeof stepFinish.part === 'object'
    ? stepFinish.part as JsonRecord
    : {};
  const finish = String(info.finish ?? info.finishReason ?? finishPart.reason ?? '');
  if (finish && !['stop', 'end_turn', 'completed'].includes(finish)) {
    throw new Error(`OpenCode model finished with unsupported reason: ${finish}.`);
  }

  const tokens = (info.tokens && typeof info.tokens === 'object' ? info.tokens
    : finishPart.tokens && typeof finishPart.tokens === 'object' ? finishPart.tokens : {}) as JsonRecord;
  const costValue = info.cost ?? finishPart.cost;
  const cost = typeof costValue === 'number' && Number.isFinite(costValue) && costValue >= 0
    ? costValue
    : undefined;
  return { text, tokens, cost, finish, providerId, modelId };
}

function numeric(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function usageFrom(tokens: JsonRecord) {
  const cache = tokens.cache && typeof tokens.cache === 'object' ? tokens.cache as JsonRecord : {};
  const input = numeric(tokens.input ?? tokens.inputTokens);
  const output = numeric(tokens.output ?? tokens.outputTokens);
  const reasoning = numeric(tokens.reasoning ?? tokens.reasoningTokens);
  const cacheRead = numeric(cache.read ?? tokens.cacheRead ?? tokens.cache_read);
  const cacheWrite = numeric(cache.write ?? tokens.cacheWrite ?? tokens.cache_write);

  const inputTokens: Record<string, number> = {};
  if (input !== undefined) inputTokens.noCache = input;
  if (cacheRead !== undefined) inputTokens.cacheRead = cacheRead;
  if (cacheWrite !== undefined) inputTokens.cacheWrite = cacheWrite;
  if (input !== undefined && cacheRead !== undefined && cacheWrite !== undefined) {
    inputTokens.total = input + cacheRead + cacheWrite;
  }
  const outputTokens: Record<string, number> = {};
  if (output !== undefined) {
    outputTokens.total = output;
    outputTokens.text = reasoning === undefined ? output : Math.max(0, output - reasoning);
  }
  if (reasoning !== undefined) outputTokens.reasoning = reasoning;
  return { inputTokens, outputTokens };
}

function firstObject(text: string): JsonRecord | null {
  const start = text.indexOf('{');
  for (let end = text.lastIndexOf('}'); start >= 0 && end > start; end = text.lastIndexOf('}', end - 1)) {
    try {
      const value: unknown = JSON.parse(text.slice(start, end + 1));
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) return value as JsonRecord;
    } catch {
      // Try the next candidate object.
    }
  }
  return null;
}

function replyContent(text: string, options: LanguageModelV4CallOptions): LanguageModelV4Content[] {
  const tools = functionTools(options);
  const choice = options.toolChoice ?? { type: 'auto' };
  const wantsCalls = tools.length > 0 && choice.type !== 'none';
  const reply = firstObject(text);
  if (wantsCalls) {
    const named = Array.isArray(reply?.tool_calls) ? reply.tool_calls as JsonRecord[] : [];
    if (named.length > 0) {
      const allowed = new Set(tools.map((tool) => tool.name));
      const parsed = named.map((call) => {
        const name = call.name;
        const input = call.input;
        if (typeof name !== 'string' || !allowed.has(name)
            || (choice.type === 'tool' && name !== choice.toolName)
            || typeof input !== 'object' || input === null || Array.isArray(input)) return null;
        return {
          type: 'tool-call' as const,
          toolCallId: `call_${randomUUID()}`,
          toolName: name,
          input: JSON.stringify(input),
        };
      });
      if (parsed.every((call) => call !== null)) return parsed as LanguageModelV4Content[];
      return [{ type: 'text', text: 'The model returned an invalid or unsupported tool call. No action was executed.' }];
    }
    if (choice.type === 'required' || choice.type === 'tool') {
      return [{ type: 'text', text: 'The model did not return the required tool call.' }];
    }
    return [{ type: 'text', text: typeof reply?.text === 'string' ? reply.text : text }];
  }

  if (options.responseFormat?.type === 'json') {
    return [{ type: 'text', text: reply ? JSON.stringify(reply) : text }];
  }
  return [{ type: 'text', text }];
}

async function generate(
  fullModelId: string,
  options: LanguageModelV4CallOptions,
): Promise<LanguageModelV4GenerateResult> {
  const { providerId, modelId } = modelParts(fullModelId);
  const binary = process.env.ADS_E2E_OPENCODE_BIN ?? 'opencode';
  const directory = await mkdtemp(join(tmpdir(), 'ads-e2e-opencode-'));
  let sessionId: string | undefined;
  let result: LanguageModelV4GenerateResult | undefined;
  let failure: Error | undefined;

  try {
    await mkdir(join(directory, '.opencode', 'agents'), { recursive: true });
    const { system, transcriptPath, attachments } = await writeTranscript(options.prompt, directory);
    const rules = replyRules(options);
    const agentBody = [system, rules].filter(Boolean).join('\n\n');
    const agentFile = [
      '---',
      'description: Model-only bridge for ADS e2e. All tool execution stays in the e2e runner.',
      'mode: primary',
      'hidden: true',
      'steps: 1',
      'permissions:',
      '  - action: "*"',
      '    resource: "*"',
      '    effect: deny',
      '---',
      agentBody,
      '',
    ].join('\n');
    await writeFile(join(directory, '.opencode', 'agents', 'ads-e2e-model.md'), agentFile, 'utf8');

    const config = {
      '$schema': 'https://opencode.ai/config.json',
      update: 'disable',
      plugins: [],
      mcp: {},
      permissions: [{ action: '*', resource: '*', effect: 'deny' }],
      policies: [
          { action: 'tool.use', resource: '*', effect: 'deny' },
          { action: 'mcp.use', resource: '*', effect: 'deny' },
          { action: 'skill.use', resource: '*', effect: 'deny' },
          { action: 'plugin.use', resource: '*', effect: 'deny' },
          { action: 'provider.use', resource: '*', effect: 'deny' },
          { action: 'provider.use', resource: providerId, effect: 'allow' },
      ],
    };
    await writeFile(join(directory, 'opencode.json'), JSON.stringify(config, null, 2), 'utf8');

    const args = [
      'run',
      '--format', 'json',
      '--model', fullModelId,
      '--agent', 'ads-e2e-model',
      '--dir', directory,
      '--file', transcriptPath,
      ...attachments.flatMap((attachment) => ['--file', attachment.path]),
      'Read the attached conversation transcript. Follow the agent instructions and return the required response only.',
    ];
    const run = await capture(binary, args, directory, { ...process.env }, options.abortSignal);
    const events = jsonLines(run.stdout);
    sessionId = sessionIdFrom(events);

    if (!sessionId) {
      const reason = run.error ? 'OpenCode CLI could not be started.'
        : run.code !== 0 ? 'OpenCode CLI exited before creating a session.'
        : 'OpenCode CLI did not report a session id.';
      throw new Error(reason);
    }

    const exportedRun = await capture(binary, ['session', 'export', sessionId], directory, { ...process.env });
    if (exportedRun.error || exportedRun.code !== 0) {
      throw new Error('OpenCode session export failed; model execution cannot be verified.');
    }
    const exported = parseJsonOutput(exportedRun.stdout);
    const stepFinish = [...events].reverse().find((event) => event.type === 'step_finish');
    const assistant = assistantResult(exported, stepFinish, providerId, modelId);

    if (run.error || run.code !== 0 || run.signal) {
      throw new Error('OpenCode CLI model execution did not complete successfully.');
    }

    const content = replyContent(assistant.text, options);
    const calledTools = content.some((part) => part.type === 'tool-call');
    const usage = usageFrom(assistant.tokens);
    const exportDigest = createHash('sha256').update(exportedRun.stdout).digest('hex');
    result = {
      content,
      finishReason: { unified: calledTools ? 'tool-calls' : 'stop', raw: assistant.finish },
      usage,
      warnings: [],
      response: { id: sessionId },
      providerMetadata: {
        'opencode-cli': {
          sessionId,
          sessionDigest: exportDigest,
          providerId,
          modelId,
          ...(assistant.cost !== undefined ? { costUsd: assistant.cost } : {}),
          sessionDeleted: true,
        },
      },
    };
  } catch (error) {
    failure = error as Error;
  } finally {
    if (sessionId) {
      const deleted = await capture(binary, ['session', 'delete', sessionId], directory, { ...process.env });
      if (deleted.error || deleted.code !== 0) {
        failure = new Error('OpenCode session cleanup failed; the run is not accepted.');
        result = undefined;
      }
    }
    await rm(directory, { recursive: true, force: true });
  }

  if (failure) throw failure;
  if (!result) throw new Error('OpenCode CLI did not produce a verified model result.');
  return result;
}
