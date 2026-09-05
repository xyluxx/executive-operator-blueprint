const fs = require('fs');
const vm = require('vm');
const { webcrypto } = require('crypto');

global.crypto = webcrypto;
global.atob = (value) => Buffer.from(value, 'base64').toString('binary');
global.btoa = (value) => Buffer.from(value, 'binary').toString('base64');

const script = fs.readFileSync(process.argv[2], 'utf8');
vm.runInThisContext(script, { filename: process.argv[2] });

(async () => {
  const publicKey = process.argv[3];
  const plaintext = process.argv[4];
  const payload = await global.SecureDropCrypto.encryptPayload(publicKey, plaintext);
  process.stdout.write(JSON.stringify(payload));
})().catch((error) => {
  process.stderr.write(error.name);
  process.exit(1);
});
