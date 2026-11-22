// Compatibility entry point. The authenticated gateway now lives in gateway_app,
// independently of RAG. No business data, fake users or JSON state are kept here.
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ownPython = path.join(__dirname, '.venv', 'Scripts', 'python.exe');
const devPython = path.join(__dirname, '..', 'chatbot', '.venv', 'Scripts', 'python.exe');
const python = process.env.GATEWAY_PYTHON || (fs.existsSync(ownPython) ? ownPython : devPython);
const child = spawn(python, ['-X', 'utf8', '-m', 'uvicorn', 'gateway_app.main:create_app', '--factory',
  '--host', process.env.GATEWAY_HOST || '127.0.0.1', '--port', process.env.PORT || '8080'],
  { cwd: __dirname, env: process.env, windowsHide: true, stdio: 'inherit' });
child.on('error', () => { console.error('Cannot start gateway Python. Configure GATEWAY_PYTHON and install gateway/requirements.txt.'); process.exitCode = 1; });
child.on('exit', (code) => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
