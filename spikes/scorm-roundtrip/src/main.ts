/**
 * Increment 1 round-trip page: save, resume, verify, score and interactions
 * against a real LMS (Canvas) or the standalone scorm-again stand-in.
 */
import {
  LOCATION_MAX,
  SUSPEND_DATA_MAX,
  buildSaveOfLength,
  decodeSave,
  formatReference,
  parseReference,
  sha256Hex,
} from './payload.ts';
import {
  STANDALONE_STORAGE_KEY,
  createStandaloneApi,
  findLmsApi,
  toScormDuration,
  toScormTime,
  type ApiMode,
  type Scorm2004Api,
} from './scormApi.ts';

const SEED = 20261020;

const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element #${id}`);
  return el as T;
};

const ui = {
  mode: $('mode'),
  entry: $('entry'),
  storedLen: $('stored-len'),
  storedRef: $('stored-ref'),
  storedScore: $('stored-score'),
  result: $('result'),
  log: $('log'),
  save30: $<HTMLButtonElement>('btn-save-30k'),
  save60: $<HTMLButtonElement>('btn-save-60k'),
  verify: $<HTMLButtonElement>('btn-verify'),
  score: $<HTMLButtonElement>('btn-score'),
  interactions: $<HTMLButtonElement>('btn-interactions'),
  exit: $<HTMLButtonElement>('btn-exit'),
  clear: $<HTMLButtonElement>('btn-clear'),
};
const actionButtons = [ui.save30, ui.save60, ui.verify, ui.score, ui.interactions, ui.exit];

let api: Scorm2004Api | null = null;
let mode: ApiMode = 'standalone';
let terminated = false;
const startedAt = Date.now();

function log(message: string): void {
  const li = document.createElement('li');
  li.textContent = `${new Date().toISOString().slice(11, 19)}  ${message}`;
  ui.log.append(li);
  ui.log.scrollTop = ui.log.scrollHeight;
}

function setResult(text: string, state: 'ok' | 'bad' | 'neutral' = 'neutral'): void {
  ui.result.textContent = text;
  ui.result.className = `result${state === 'neutral' ? '' : ` ${state}`}`;
}

function setBusy(busy: boolean): void {
  for (const b of actionButtons) b.disabled = busy || terminated || api === null;
}

function requireApi(): Scorm2004Api {
  if (!api) throw new Error('SCORM API not initialized');
  return api;
}

function errorDetail(a: Scorm2004Api): string {
  const code = a.GetLastError();
  if (code === '0') return '';
  return ` [error ${code}: ${a.GetErrorString(code)}; ${a.GetDiagnostic(code)}]`;
}

/** SetValue with logging; returns true on success. */
function set(element: string, value: string): boolean {
  const a = requireApi();
  const ok = a.SetValue(element, value) === 'true';
  const shown = value.length > 80 ? `<${value.length} chars>` : JSON.stringify(value);
  log(`SetValue(${element}, ${shown}) -> ${ok}${ok ? '' : errorDetail(a)}`);
  return ok;
}

function get(element: string): string {
  const a = requireApi();
  const v = a.GetValue(element);
  const err = errorDetail(a);
  const shown = v.length > 80 ? `<${v.length} chars>` : JSON.stringify(v);
  log(`GetValue(${element}) -> ${shown}${err}`);
  return v;
}

function commit(): boolean {
  const a = requireApi();
  const ok = a.Commit('') === 'true';
  log(`Commit() -> ${ok}${ok ? '' : errorDetail(a)}`);
  return ok;
}

function refreshStored(): void {
  const data = get('cmi.suspend_data');
  ui.storedLen.textContent = data ? `${data.length} characters` : '(empty)';
  ui.storedRef.textContent = get('cmi.location') || '(empty)';
  ui.storedScore.textContent = get('cmi.score.scaled') || '(none)';
}

async function save(target: number): Promise<void> {
  const { save: data, days } = await buildSaveOfLength(target, SEED, SUSPEND_DATA_MAX);
  const hash = await sha256Hex(data);
  const ref = formatReference(data, hash);
  if (ref.length > LOCATION_MAX) throw new Error('Reference too long for cmi.location');
  log(`Built save: ${data.length} characters (${days} mock days), sha256 ${hash}`);

  const okData = set('cmi.suspend_data', data);
  const okRef = set('cmi.location', ref);
  const okExit = set('cmi.exit', 'suspend');
  const okCommit = commit();

  // Same-session read-back catches LMSs that truncate on write.
  const back = get('cmi.suspend_data');
  const backHash = await sha256Hex(back);
  refreshStored();
  const sameSession = back.length === data.length && backHash === hash;

  if (okData && okRef && okExit && okCommit && sameSession) {
    setResult(
      `Saved ${data.length} characters. Reference sha256 starts ${hash.slice(0, 12)}. ` +
        'Now use "Exit session", close this window and relaunch.',
      'ok',
    );
  } else {
    setResult(
      `SAVE PROBLEM: SetValue data=${okData}, location=${okRef}, exit=${okExit}, ` +
        `commit=${okCommit}; read-back ${back.length}/${data.length} characters, ` +
        `checksum ${sameSession ? 'matches' : 'differs'}.`,
      'bad',
    );
  }
}

async function verify(): Promise<void> {
  const data = get('cmi.suspend_data');
  const refText = get('cmi.location');
  const ref = parseReference(refText);
  if (!data) {
    setResult('MISMATCH: no saved data was returned (cmi.suspend_data is empty).', 'bad');
    return;
  }
  if (!ref) {
    setResult(`MISMATCH: reference in cmi.location is missing or invalid (${refText.length} characters).`, 'bad');
    return;
  }
  const hash = await sha256Hex(data);
  let decoded = 'decodes OK';
  try {
    const state = await decodeSave(data);
    decoded = `decodes OK (${state.days} mock days)`;
  } catch (err) {
    decoded = `does NOT decode: ${String(err)}`;
  }
  const match = data.length === ref.len && hash === ref.sha256;
  log(`Verify: expected len ${ref.len} sha256 ${ref.sha256}`);
  log(`Verify: received len ${data.length} sha256 ${hash}; ${decoded}`);
  setResult(
    match
      ? `MATCH: ${data.length} of ${ref.len} characters, sha256 ${hash.slice(0, 12)}…; ${decoded}.`
      : `MISMATCH: received ${data.length} of ${ref.len} characters, sha256 ${hash.slice(0, 12)}… ` +
          `vs expected ${ref.sha256.slice(0, 12)}…; ${decoded}.`,
    match ? 'ok' : 'bad',
  );
}

function reportScore(): void {
  const results = [
    set('cmi.score.min', '0'),
    set('cmi.score.max', '100'),
    set('cmi.score.raw', '87'),
    set('cmi.score.scaled', '0.87'),
    set('cmi.completion_status', 'completed'),
    set('cmi.success_status', 'passed'),
    set('cmi.session_time', toScormDuration(Date.now() - startedAt)),
    set('cmi.exit', 'suspend'),
    commit(),
  ];
  refreshStored();
  const ok = results.every(Boolean);
  setResult(
    ok
      ? 'Score sent: scaled 0.87 (87 out of 100), completed, passed. Check the Canvas gradebook.'
      : 'SCORE PROBLEM: at least one call failed. See the log.',
    ok ? 'ok' : 'bad',
  );
}

function writeInteractions(): void {
  const start = Number(get('cmi.interactions._count')) || 0;
  const records = [
    { id: 'urn:agroeco:y1:field1:corn-yield-bu-ac', value: '182.5', text: 'Year 1 field 1 corn yield (bu/ac)' },
    { id: 'urn:agroeco:y1:net-income-usd', value: '41250.75', text: 'Year 1 net farm income (USD)' },
    { id: 'urn:agroeco:y1:n-leached-kg-ha', value: '23.4', text: 'Year 1 nitrogen leached (kg/ha)' },
  ];
  const now = toScormTime(new Date());
  let ok = true;
  records.forEach((r, i) => {
    const n = start + i;
    ok = set(`cmi.interactions.${n}.id`, r.id) && ok;
    ok = set(`cmi.interactions.${n}.type`, 'numeric') && ok;
    ok = set(`cmi.interactions.${n}.description`, r.text) && ok;
    ok = set(`cmi.interactions.${n}.learner_response`, r.value) && ok;
    ok = set(`cmi.interactions.${n}.result`, 'neutral') && ok;
    ok = set(`cmi.interactions.${n}.timestamp`, now) && ok;
  });
  ok = commit() && ok;
  const count = get('cmi.interactions._count');
  setResult(
    ok
      ? `Interaction records written: 3 (LMS now reports ${count}).`
      : 'INTERACTION PROBLEM: at least one call failed. See the log.',
    ok ? 'ok' : 'bad',
  );
}

function terminate(reason: string): void {
  if (!api || terminated) return;
  set('cmi.session_time', toScormDuration(Date.now() - startedAt));
  set('cmi.exit', 'suspend');
  const ok = api.Terminate('') === 'true';
  log(`Terminate() [${reason}] -> ${ok}${ok ? '' : errorDetail(api)}`);
  terminated = true;
  setBusy(false);
}

async function run(action: () => void | Promise<void>): Promise<void> {
  setBusy(true);
  try {
    await action();
  } catch (err) {
    log(`ERROR: ${String(err)}`);
    setResult(`ERROR: ${String(err)}`, 'bad');
  } finally {
    setBusy(false);
  }
}

async function start(): Promise<void> {
  const lms = findLmsApi(window);
  if (lms) {
    api = lms;
    mode = 'lms';
  } else {
    api = await createStandaloneApi(window.localStorage);
    mode = 'standalone';
    ui.clear.hidden = false;
  }
  ui.mode.textContent =
    mode === 'lms' ? 'LMS (API_1484_11 found)' : 'Standalone (scorm-again stand-in, no LMS)';
  log(`Mode: ${mode}`);

  const ok = api.Initialize('') === 'true';
  log(`Initialize() -> ${ok}${ok ? '' : errorDetail(api)}`);
  if (!ok) {
    setResult('Initialize failed. See the log.', 'bad');
    api = null;
    return;
  }
  ui.entry.textContent = get('cmi.entry') || '(empty)';
  refreshStored();
  setBusy(false);

  if (get('cmi.suspend_data')) {
    await run(verify);
  } else {
    setResult('Connected. No saved data yet: choose a Save action.', 'neutral');
  }
}

ui.save30.addEventListener('click', () => void run(() => save(30000)));
ui.save60.addEventListener('click', () => void run(() => save(60000)));
ui.verify.addEventListener('click', () => void run(verify));
ui.score.addEventListener('click', () => void run(reportScore));
ui.interactions.addEventListener('click', () => void run(writeInteractions));
ui.exit.addEventListener('click', () => {
  terminate('exit button');
  setResult('Session ended (suspend). Close this window, then relaunch the assignment.', 'ok');
});
ui.clear.addEventListener('click', () => {
  window.localStorage.removeItem(STANDALONE_STORAGE_KEY);
  log('Standalone data cleared. Reload to start fresh.');
  setResult('Standalone data cleared. Reload the page to start fresh.', 'neutral');
});
window.addEventListener('pagehide', () => terminate('pagehide'));

start().catch((err: unknown) => {
  log(`ERROR during start: ${String(err)}`);
  setResult(`ERROR during start: ${String(err)}`, 'bad');
});
