/** Tests for the SCORM zip packager (node --test). */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { inflateRawSync } from 'node:zlib';
import { buildManifest, buildZip, packageDist } from '../scripts/package.mjs';

test('manifest declares SCORM 2004 3rd Edition and one SCO at index.html', () => {
  const xml = buildManifest(['index.html', 'assets/app.js']);
  assert.match(xml, /<schemaversion>2004 3rd Edition<\/schemaversion>/);
  assert.match(xml, /adlcp:scormType="sco" href="index.html"/);
  assert.match(xml, /<file href="assets\/app.js"\/>/);
  assert.throws(() => buildManifest(['other.html']));
});

test('zip entries round-trip and are deterministic', () => {
  const entries = [
    { name: 'a.txt', data: Buffer.from('hello '.repeat(100)) },
    { name: 'dir/b.bin', data: Buffer.from([0, 1, 2, 3, 255]) },
  ];
  const zip = buildZip(entries);
  assert.deepEqual(zip, buildZip(entries));
  // Parse the first local header and inflate it.
  assert.equal(zip.readUInt32LE(0), 0x04034b50);
  const compSize = zip.readUInt32LE(18);
  const nameLen = zip.readUInt16LE(26);
  const name = zip.subarray(30, 30 + nameLen).toString('utf8');
  assert.equal(name, 'a.txt');
  const body = zip.subarray(30 + nameLen, 30 + nameLen + compSize);
  assert.equal(inflateRawSync(body).toString(), 'hello '.repeat(100));
  // End-of-central-directory record reports 2 entries.
  assert.equal(zip.readUInt32LE(zip.length - 22), 0x06054b50);
  assert.equal(zip.readUInt16LE(zip.length - 12), 2);
});

test('packageDist puts imsmanifest.xml at the zip root', () => {
  const dir = mkdtempSync(join(tmpdir(), 'scorm-pkg-'));
  const dist = join(dir, 'dist');
  mkdirSync(join(dist, 'assets'), { recursive: true });
  writeFileSync(join(dist, 'index.html'), '<!doctype html><title>t</title>');
  writeFileSync(join(dist, 'assets', 'x.js'), 'console.log(1)');
  const out = join(dir, 'out.zip');
  const r = packageDist(dist, out, '9.9.9');
  assert.equal(r.files, 3);
  const zip = readFileSync(out);
  const nameLen = zip.readUInt16LE(26);
  assert.equal(zip.subarray(30, 30 + nameLen).toString(), 'imsmanifest.xml');
  // Cross-check with an independent zip reader when Python is available.
  try {
    const listing = execFileSync('python3', ['-m', 'zipfile', '-t', out], { encoding: 'utf8' });
    assert.match(listing, /Done testing/);
  } catch (err) {
    if (err && err.code !== 'ENOENT') throw err;
  }
});
