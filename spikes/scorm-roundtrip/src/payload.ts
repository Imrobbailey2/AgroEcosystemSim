/**
 * Save-payload helpers for the SCORM round-trip spike.
 *
 * A "save" is: SAVE_PREFIX + base64(deflate-raw(JSON(mock farm state))).
 * The checksum is SHA-256 (hex) of the exact save string that is written to
 * cmi.suspend_data, so any truncation or re-encoding by the LMS is detected.
 *
 * Pure module: no DOM or SCORM access, so it runs in browsers and in Node 22+.
 */

export const SAVE_PREFIX = 'AGS1.';
/** SCORM 2004 3rd Edition SPM for cmi.suspend_data. */
export const SUSPEND_DATA_MAX = 64000;
/** cmi.location SPM in SCORM 2004. */
export const LOCATION_MAX = 1000;

export interface MockFarmState {
  v: 1;
  seed: number;
  days: number;
  /** Per-day rows: [day, soilWaterMm, etMm, soilNKgHa, cashUsd]. */
  log: number[][];
}

/** Small, fast, seeded PRNG (mulberry32). Returns floats in [0, 1). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round = (x: number, dp: number): number => {
  const f = 10 ** dp;
  return Math.round(x * f) / f;
};

/** Build a deterministic mock farm state with `days` daily rows. */
export function buildMockState(seed: number, days: number): MockFarmState {
  if (!Number.isInteger(days) || days < 1) {
    throw new RangeError(`days must be a positive integer, got ${days}`);
  }
  const rand = mulberry32(seed);
  const log: number[][] = [];
  let cash = 250000;
  for (let d = 0; d < days; d++) {
    cash += round((rand() - 0.55) * 900, 2);
    log.push([
      d,
      round(20 + rand() * 80, 2),
      round(rand() * 7, 3),
      round(rand() * 180, 2),
      round(cash, 2),
    ]);
  }
  return { v: 1, seed, days, log };
}

async function transform(
  bytes: BufferSource,
  stream: CompressionStream | DecompressionStream,
): Promise<ArrayBuffer> {
  // Write and read concurrently (avoids back-pressure deadlock) and await both,
  // so a failure on either side rejects here instead of becoming unhandled.
  const writer = stream.writable.getWriter();
  const written = writer.write(bytes).then(() => writer.close());
  const read = new Response(stream.readable).arrayBuffer();
  const [, out] = await Promise.all([written, read]);
  return out;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

const BASE64_RE = /^[A-Za-z0-9+/]*={0,2}$/;

export function base64ToBytes(b64: string): Uint8Array {
  if (b64.length % 4 !== 0 || !BASE64_RE.test(b64)) {
    throw new Error('Save data is not valid base64 (possibly truncated).');
  }
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/** Encode a state into a suspend_data-safe ASCII string. */
export async function encodeSave(state: MockFarmState): Promise<string> {
  const json = new TextEncoder().encode(JSON.stringify(state));
  const compressed = await transform(json, new CompressionStream('deflate-raw'));
  return SAVE_PREFIX + bytesToBase64(new Uint8Array(compressed));
}

/** Decode and shape-check a save string. Throws on any corruption. */
export async function decodeSave(save: string): Promise<MockFarmState> {
  if (!save.startsWith(SAVE_PREFIX)) {
    throw new Error(`Save data does not start with ${SAVE_PREFIX}`);
  }
  const bytes = base64ToBytes(save.slice(SAVE_PREFIX.length));
  let inflated: ArrayBuffer;
  try {
    inflated = await transform(bytes as BufferSource, new DecompressionStream('deflate-raw'));
  } catch (err) {
    throw new Error(`Save data failed to decompress: ${String(err)}`);
  }
  const parsed: unknown = JSON.parse(new TextDecoder().decode(inflated));
  const s = parsed as Partial<MockFarmState>;
  if (
    s.v !== 1 ||
    !Array.isArray(s.log) ||
    s.log.length !== s.days ||
    typeof s.seed !== 'number'
  ) {
    throw new Error('Save data decoded but has an unexpected shape.');
  }
  return s as MockFarmState;
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

export interface SizedSave {
  save: string;
  days: number;
}

/**
 * Smallest deterministic save whose length is >= `target` characters.
 * Throws if that save would exceed `max` (the SCORM SPM).
 */
export async function buildSaveOfLength(
  target: number,
  seed: number,
  max: number = SUSPEND_DATA_MAX,
): Promise<SizedSave> {
  if (target > max) throw new RangeError(`target ${target} exceeds max ${max}`);
  const saveFor = (days: number): Promise<string> => encodeSave(buildMockState(seed, days));

  let lo = 1;
  let hi = 64;
  let hiSave = await saveFor(hi);
  while (hiSave.length < target) {
    lo = hi;
    hi *= 2;
    hiSave = await saveFor(hi);
  }
  // Invariant: save(hi).length >= target; find the smallest such hi.
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    const midSave = await saveFor(mid);
    if (midSave.length >= target) {
      hi = mid;
      hiSave = midSave;
    } else {
      lo = mid;
    }
  }
  if (hiSave.length > max) {
    throw new RangeError(`Could not build a save between ${target} and ${max} characters.`);
  }
  return { save: hiSave, days: hi };
}

/** Reference stored in cmi.location so the relaunch can verify suspend_data. */
export function formatReference(save: string, sha256: string): string {
  return `ags1;len=${save.length};sha256=${sha256}`;
}

export interface SaveReference {
  len: number;
  sha256: string;
}

export function parseReference(text: string): SaveReference | null {
  const m = /^ags1;len=(\d+);sha256=([0-9a-f]{64})$/.exec(text);
  if (!m || m[1] === undefined || m[2] === undefined) return null;
  return { len: Number(m[1]), sha256: m[2] };
}
