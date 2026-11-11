import { readFileSync, existsSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export function neonEnvironment(parent = process.env) {
  const envFile = parent.KEDR_NEON_ENV_FILE
    ? resolve(parent.KEDR_NEON_ENV_FILE)
    : join(root, existsSync(join(root, '.env')) ? '.env' : '.env.local');
  if (!existsSync(envFile)) throw new Error('Run neon deploy to pull the Neon environment first.');
  const values = parseEnv(readFileSync(envFile, 'utf8'));
  const pooled = values.DATABASE_URL;
  const direct = values.DATABASE_URL_UNPOOLED;
  for (const value of [pooled, direct]) {
    if (!value) throw new Error('The Neon environment needs DATABASE_URL and DATABASE_URL_UNPOOLED.');
    const url = new URL(value);
    if (!['postgres:', 'postgresql:'].includes(url.protocol)
        || !['require', 'verify-ca', 'verify-full'].includes(url.searchParams.get('sslmode'))) {
      throw new Error('Neon database URLs must use PostgreSQL with TLS enabled.');
    }
  }
  const pythonDirectory = join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin');
  const portableGit = join(root, 'tools/share-tools/git/cmd');
  const paths = [pythonDirectory, dirname(process.execPath), ...(existsSync(portableGit) ? [portableGit] : []), parent.PATH || ''];
  return {
    envFile,
    branch: values.NEON_BRANCH || 'configured branch',
    python: join(pythonDirectory, process.platform === 'win32' ? 'python.exe' : 'python'),
    env: {
      ...parent,
      PATH: paths.join(process.platform === 'win32' ? ';' : ':'),
      ...values,
      KEDR_DATABASE_URL: pooled,
      KEDR_MIGRATION_DATABASE_URL: direct,
      KEDR_JOB_MODE: 'durable',
      KEDR_DATA_DIR: join(root, '.tmp/neon-runtime'),
      KEDR_LEGACY_ROOT: '',
      KEDR_AI_PROVIDER: 'disabled',
      KEDR_SECURE_COOKIES: '0',
      KEDR_ALLOWED_ORIGINS: 'http://127.0.0.1:3000,http://localhost:3000',
      CRON_SECRET: parent.CRON_SECRET || randomBytes(32).toString('hex'),
    },
  };
}
