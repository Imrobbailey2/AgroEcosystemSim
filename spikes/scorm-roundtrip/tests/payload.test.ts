/**
 * Unit tests for the save payload (run with `node --test`; Node 22.18+ strips types).
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  SAVE_PREFIX,
  SUSPEND_DATA_MAX,
  buildMockState,
  buildSaveOfLength,
  decodeSave,
  encodeSave,
  formatReference,
  parseReference,
  sha256Hex,
} from '../src/payload.ts';

const SEED = 20261020;

test('mock state is deterministic for a seed', () => {
  assert.deepEqual(buildMockState(SEED, 50), buildMockState(SEED, 50));
  assert.notDeepEqual(buildMockState(SEED, 50), buildMockState(SEED + 1, 50));
});

test('encode/decode round-trips exactly', async () => {
  const state = buildMockState(SEED, 300);
  const save = await encodeSave(state);
  assert.ok(save.startsWith(SAVE_PREFIX));
  assert.match(save.slice(SAVE_PREFIX.length), /^[A-Za-z0-9+/]+=*$/);
  assert.deepEqual(await decodeSave(save), state);
});

for (const target of [30000, 60000]) {
  test(`builds a save of at least ${target} chars within the SPM`, async () => {
    const { save, days } = await buildSaveOfLength(target, SEED);
    assert.ok(save.length >= target, `length ${save.length}`);
    assert.ok(save.length <= SUSPEND_DATA_MAX, `length ${save.length}`);
    const again = await buildSaveOfLength(target, SEED);
    assert.equal(again.save, save, 'same seed and target give the same save');
    assert.equal((await decodeSave(save)).days, days);
  });
}

test('truncated saves are rejected', async () => {
  const { save } = await buildSaveOfLength(30000, SEED);
  await assert.rejects(decodeSave(save.slice(0, 20000)));
  await assert.rejects(decodeSave(save.slice(0, 20001)));
  await assert.rejects(decodeSave('garbage'));
});

test('checksum reference round-trips and detects change', async () => {
  const save = await encodeSave(buildMockState(SEED, 100));
  const hash = await sha256Hex(save);
  assert.equal(hash.length, 64);
  const ref = formatReference(save, hash);
  assert.ok(ref.length < 1000);
  assert.deepEqual(parseReference(ref), { len: save.length, sha256: hash });
  assert.notEqual(await sha256Hex(save.slice(0, -1)), hash);
  assert.equal(parseReference('nonsense'), null);
});
