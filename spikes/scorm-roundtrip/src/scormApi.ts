/**
 * SCORM 2004 API discovery plus a standalone stand-in.
 *
 * In Canvas the LMS exposes `API_1484_11` on a parent (or opener) window.
 * When none is found, a stand-in built on scorm-again is used and the key
 * values are persisted to localStorage so save/resume can be tested offline.
 */

/** The eight SCORM 2004 run-time API methods. */
export interface Scorm2004Api {
  Initialize(param: string): string;
  Terminate(param: string): string;
  GetValue(element: string): string;
  SetValue(element: string, value: string): string;
  Commit(param: string): string;
  GetLastError(): string;
  GetErrorString(code: string): string;
  GetDiagnostic(code: string): string;
}

export type ApiMode = 'lms' | 'standalone';

const MAX_DEPTH = 500;

function isApi(candidate: unknown): candidate is Scorm2004Api {
  if (typeof candidate !== 'object' || candidate === null) return false;
  const c = candidate as Record<string, unknown>;
  return (
    typeof c.Initialize === 'function' &&
    typeof c.GetValue === 'function' &&
    typeof c.SetValue === 'function' &&
    typeof c.Commit === 'function'
  );
}

function apiOn(win: Window): Scorm2004Api | null {
  try {
    const candidate = (win as unknown as { API_1484_11?: unknown }).API_1484_11;
    return isApi(candidate) ? candidate : null;
  } catch {
    return null; // cross-origin frame
  }
}

function searchUp(start: Window): Scorm2004Api | null {
  let win: Window = start;
  for (let depth = 0; depth < MAX_DEPTH; depth++) {
    const found = apiOn(win);
    if (found) return found;
    let parent: Window;
    try {
      parent = win.parent;
    } catch {
      return null;
    }
    if (!parent || parent === win) return null;
    win = parent;
  }
  return null;
}

/** Standard ADL discovery: this window's parents, then the opener's parents. */
export function findLmsApi(win: Window): Scorm2004Api | null {
  const fromParents = searchUp(win);
  if (fromParents) return fromParents;
  let opener: Window | null = null;
  try {
    opener = win.opener as Window | null;
  } catch {
    opener = null;
  }
  return opener ? searchUp(opener) : null;
}

export const STANDALONE_STORAGE_KEY = 'agroeco-scorm-roundtrip:standalone-cmi';

/** Read/write elements persisted by the stand-in between page loads. */
const PERSISTED = [
  'cmi.suspend_data',
  'cmi.location',
  'cmi.score.scaled',
  'cmi.score.raw',
  'cmi.score.min',
  'cmi.score.max',
  'cmi.completion_status',
  'cmi.success_status',
] as const;

interface StoredCmi {
  exit: string;
  values: Record<string, string>;
}

function readStored(storage: Storage): StoredCmi | null {
  try {
    const raw = storage.getItem(STANDALONE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredCmi>;
    if (typeof parsed.exit !== 'string' || typeof parsed.values !== 'object' || !parsed.values) {
      return null;
    }
    return { exit: parsed.exit, values: parsed.values };
  } catch {
    return null;
  }
}

/**
 * Wrap a scorm-again Scorm2004API so it behaves like an LMS across reloads:
 * values are restored after Initialize, `cmi.entry` reports "resume" after a
 * suspended exit, and state is persisted on Commit and Terminate.
 */
export async function createStandaloneApi(storage: Storage): Promise<Scorm2004Api> {
  const { Scorm2004API } = await import('scorm-again');
  const inner = new Scorm2004API({}) as unknown as Scorm2004Api;
  const stored = readStored(storage);
  let exit = '';

  const persist = (): void => {
    const values: Record<string, string> = {};
    for (const el of PERSISTED) {
      const v = inner.GetValue(el);
      if (v !== '') values[el] = v;
    }
    try {
      storage.setItem(STANDALONE_STORAGE_KEY, JSON.stringify({ exit, values }));
    } catch (err) {
      console.error('Standalone stand-in could not persist state', err);
    }
  };

  return {
    Initialize(param) {
      const result = inner.Initialize(param);
      if (result === 'true' && stored && stored.exit === 'suspend') {
        for (const [el, v] of Object.entries(stored.values)) inner.SetValue(el, v);
      }
      return result;
    },
    GetValue(element) {
      if (element === 'cmi.entry') {
        return stored && stored.exit === 'suspend' ? 'resume' : 'ab-initio';
      }
      return inner.GetValue(element);
    },
    SetValue(element, value) {
      const result = inner.SetValue(element, value);
      if (element === 'cmi.exit' && result === 'true') exit = value;
      return result;
    },
    Commit(param) {
      persist();
      return inner.Commit(param);
    },
    Terminate(param) {
      persist();
      return inner.Terminate(param);
    },
    GetLastError: () => inner.GetLastError(),
    GetErrorString: (code) => inner.GetErrorString(code),
    GetDiagnostic: (code) => inner.GetDiagnostic(code),
  };
}

/** Format a SCORM 2004 timeinterval (ISO 8601 duration), e.g. "PT75.5S". */
export function toScormDuration(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 10) / 100);
  return `PT${seconds}S`;
}

/** SCORM 2004 time (second,10,0): at most 2 fractional digits, UTC. */
export function toScormTime(date: Date): string {
  return `${date.toISOString().slice(0, 19)}.0Z`;
}
