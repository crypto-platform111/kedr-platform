import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';
import { neonEnvironment, root } from './neon-environment.mjs';

try {
  const setup = neonEnvironment();
  const localCli = process.env.KEDR_VERCEL_CLI_PATH || join(root, 'tools/vercel-cli/node_modules/vercel/dist/vc.js');
  const npxCli = join(dirname(process.execPath), 'node_modules/npm/bin/npx-cli.js');
  const args = existsSync(localCli)
    ? [localCli]
    : [npxCli, '--yes', 'vercel@65.8.0'];
  if (!existsSync(args[0])) throw new Error('Install the complete Node.js 24 distribution including npm.');
  console.log(`Starting KEDR with Neon branch ${setup.branch}; database credentials stay server-side.`);
  const child = spawn(process.execPath,
    [...args, 'dev', '--local', '--listen', '127.0.0.1:3000'],
    { cwd: root, env: setup.env, stdio: 'inherit' });
  child.on('error', () => { console.error('Unable to start the local Vercel services.'); process.exitCode = 1; });
  child.on('exit', code => { process.exitCode = code ?? 1; });
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
