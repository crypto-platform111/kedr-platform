import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { neonEnvironment } from '../scripts/neon-environment.mjs';

function fixture(t, contents) {
  const directory = mkdtempSync(join(tmpdir(), 'kedr-neon-env-'));
  t.after(() => {
    assert.ok(resolve(directory).startsWith(resolve(tmpdir()) + sep));
    rmSync(directory, { recursive: true });
  });
  const file = join(directory, '.env.local');
  writeFileSync(file, contents);
  return file;
}
const pooled = 'postgresql://u:x@fixture-pooler.example.invalid/neondb?sslmode=require';
const direct = 'postgresql://u:x@fixture.example.invalid/neondb?sslmode=require';

test('Neon launch maps only the selected env file to server database configuration', t => {
  const file = fixture(t, `DATABASE_URL="${pooled}"\nDATABASE_URL_UNPOOLED='${direct}'\nNEON_BRANCH=fixture\n`);
  const setup = neonEnvironment({ KEDR_NEON_ENV_FILE: file, DATABASE_URL: 'unrelated', KEDR_LEGACY_ROOT: 'unrelated' });
  assert.equal(setup.env.KEDR_DATABASE_URL, pooled);
  assert.equal(setup.env.KEDR_MIGRATION_DATABASE_URL, direct);
  assert.equal(setup.env.KEDR_JOB_MODE, 'durable');
  assert.equal(setup.env.KEDR_LEGACY_ROOT, '');
  assert.equal(setup.env.KEDR_AI_PROVIDER, 'disabled');
  assert.equal(setup.branch, 'fixture');
  assert.equal(setup.env.CRON_SECRET.length, 64);
  assert.equal(setup.env.VITE_DATABASE_URL, undefined);
});
test('Neon launch requires the direct migration URL instead of silently using another database', t => {
  const file = fixture(t, `DATABASE_URL=${pooled}\n`);
  assert.throws(() => neonEnvironment({ KEDR_NEON_ENV_FILE: file }), /DATABASE_URL_UNPOOLED/);
});
test('Neon launch rejects non-TLS database credentials before opening a connection', t => {
  const file = fixture(t, `DATABASE_URL=${pooled.replace('require', 'disable')}\nDATABASE_URL_UNPOOLED=${direct}\n`);
  assert.throws(() => neonEnvironment({ KEDR_NEON_ENV_FILE: file }), /TLS/);
});
