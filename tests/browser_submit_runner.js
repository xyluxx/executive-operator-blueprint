const fs = require('fs');
const { webcrypto } = require('crypto');

globalThis.crypto = webcrypto;
globalThis.atob = (value) => Buffer.from(value, 'base64').toString('binary');
globalThis.btoa = (value) => Buffer.from(value, 'binary').toString('base64');

const source = fs.readFileSync(process.argv[2], 'utf8');
const publicKey = process.argv[3];
let submitHandler = null;
const button = { disabled: false };
const textarea = { value: 'browser-fixture-value' };
const panel = { innerHTML: '' };
const form = {
  dataset: { publicKey, prefix: '' },
  addEventListener: (_name, handler) => { submitHandler = handler; },
  querySelector: () => button,
};

globalThis.document = {
  getElementById: (id) => (id === 'drop' ? form : textarea),
  querySelector: (selector) => (selector === '.panel-inner' ? panel : null),
};
globalThis.location = { pathname: '/d/browser-fixture-token' };
globalThis.fetch = async () => ({ ok: true });

eval(source);
if (!submitHandler) throw new Error('submit handler was not registered');

submitHandler({ preventDefault() {} }).then(() => {
  process.stdout.write(JSON.stringify({
    textarea: textarea.value,
    panel: panel.innerHTML,
    disabled: button.disabled,
  }));
}).catch((error) => {
  process.stderr.write(String(error));
  process.exit(1);
});
