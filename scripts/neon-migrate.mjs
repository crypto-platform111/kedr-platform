import { spawnSync } from 'node:child_process';
import { neonEnvironment, root } from './neon-environment.mjs';

try {
  const setup = neonEnvironment();
  const env = { ...setup.env, KEDR_DATABASE_URL: setup.env.KEDR_MIGRATION_DATABASE_URL };
  const result = spawnSync(setup.python, ['-c',
    'from backend.app.db import Database; Database(".tmp/neon-runtime").initialize(); print("Neon PostgreSQL: all six application migrations applied or already present.")',
  ], { cwd: root, env, stdio: 'inherit' });
  if (result.error) throw new Error('Project Python is unavailable; run scripts/setup.ps1 first.');
  process.exitCode = result.status ?? 1;
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
