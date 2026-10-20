/**
 * Package dist/ as a SCORM 2004 3rd Edition zip (no dependencies).
 *
 *   node scripts/package.mjs [distDir] [outFile]
 *
 * Writes imsmanifest.xml at the zip root listing every file, using fixed
 * timestamps so the same build always gives a byte-identical zip.
 */
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { crc32, deflateRawSync } from 'node:zlib';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

export const MANIFEST_ID = 'edu.ufl.agroecosystemsim.scorm-roundtrip';

const xmlEscape = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** Build a SCORM 2004 3rd Edition manifest with one SCO launched at index.html. */
export function buildManifest(files, version = '0.1.0') {
  if (!files.includes('index.html')) throw new Error('dist must contain index.html');
  const fileLines = files
    .filter((f) => f !== 'imsmanifest.xml')
    .map((f) => `      <file href="${xmlEscape(f)}"/>`)
    .join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="${MANIFEST_ID}" version="${xmlEscape(version)}"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
  xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"
  xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"
  xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd http://www.adlnet.org/xsd/adlseq_v1p3 adlseq_v1p3.xsd http://www.adlnet.org/xsd/adlnav_v1p3 adlnav_v1p3.xsd http://www.imsglobal.org/xsd/imsss imsss_v1p0.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 3rd Edition</schemaversion>
  </metadata>
  <organizations default="ORG-1">
    <organization identifier="ORG-1">
      <title>AgroEcosystemSim - SCORM round-trip test</title>
      <item identifier="ITEM-1" identifierref="RES-1">
        <title>SCORM round-trip test</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-1" type="webcontent" adlcp:scormType="sco" href="index.html">
${fileLines}
    </resource>
  </resources>
</manifest>
`;
}

function u16(n) {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(n);
  return b;
}
function u32(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n >>> 0);
  return b;
}

// 1980-01-01 00:00:00 in DOS format, for reproducible zips.
const DOS_TIME = 0;
const DOS_DATE = (0 << 9) | (1 << 5) | 1;

/** Create a deflate zip from [{ name, data: Buffer }]. */
export function buildZip(entries) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const nameBuf = Buffer.from(name, 'utf8');
    const compressed = deflateRawSync(data, { level: 9 });
    const crc = crc32(data);
    const common = [
      u16(20), // version needed
      u16(0x0800), // flags: UTF-8 names
      u16(8), // deflate
      u16(DOS_TIME),
      u16(DOS_DATE),
      u32(crc),
      u32(compressed.length),
      u32(data.length),
      u16(nameBuf.length),
      u16(0), // extra length
    ];
    const local = Buffer.concat([u32(0x04034b50), ...common, nameBuf, compressed]);
    const central = Buffer.concat([
      u32(0x02014b50),
      u16(20), // version made by
      ...common,
      u16(0), // comment length
      u16(0), // disk number
      u16(0), // internal attrs
      u32(0), // external attrs
      u32(offset),
      nameBuf,
    ]);
    locals.push(local);
    centrals.push(central);
    offset += local.length;
  }
  const centralBuf = Buffer.concat(centrals);
  const end = Buffer.concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(entries.length),
    u16(entries.length),
    u32(centralBuf.length),
    u32(offset),
    u16(0),
  ]);
  return Buffer.concat([...locals, centralBuf, end]);
}

function listFiles(dir) {
  const out = [];
  const walk = (d) => {
    for (const name of readdirSync(d).sort()) {
      const full = join(d, name);
      if (statSync(full).isDirectory()) walk(full);
      else out.push(relative(dir, full).split(sep).join('/'));
    }
  };
  walk(dir);
  return out;
}

export function packageDist(distDir, outFile, version) {
  const files = listFiles(distDir).filter((f) => f !== 'imsmanifest.xml');
  const manifest = buildManifest(files, version);
  const entries = [
    { name: 'imsmanifest.xml', data: Buffer.from(manifest, 'utf8') },
    ...files.map((f) => ({ name: f, data: readFileSync(join(distDir, f)) })),
  ];
  const zip = buildZip(entries);
  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, zip);
  return { files: entries.length, bytes: zip.length, sha256: createHash('sha256').update(zip).digest('hex') };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const distDir = resolve(process.argv[2] ?? join(ROOT, 'dist'));
  const outFile = resolve(process.argv[3] ?? join(ROOT, 'artifacts', 'agroeco-scorm-roundtrip.zip'));
  const { version } = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
  try {
    const r = packageDist(distDir, outFile, version);
    console.log(`Wrote ${outFile}: ${r.files} files, ${r.bytes} bytes, sha256 ${r.sha256}`);
  } catch (err) {
    console.error(`Packaging failed: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }
}
