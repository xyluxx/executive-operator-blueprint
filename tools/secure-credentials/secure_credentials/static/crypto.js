function decode64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function encode64(value) {
  const bytes = new Uint8Array(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function encryptPayload(publicKeyB64, value) {
  const publicKey = await crypto.subtle.importKey(
    'spki',
    decode64(publicKeyB64),
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  );
  const aesKey = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    new TextEncoder().encode(value),
  );
  const rawKey = await crypto.subtle.exportKey('raw', aesKey);
  const wrappedKey = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, rawKey);
  return {
    ciphertext: encode64(ciphertext),
    iv: encode64(iv),
    wrapped_key: encode64(wrappedKey),
  };
}

globalThis.SecureDropCrypto = { encryptPayload };

const form = typeof document === 'undefined' ? null : document.getElementById('drop');
if (form) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button');
    const textarea = document.getElementById('credentials');
    const value = textarea.value;
    if (!value.trim()) return;
    button.disabled = true;

    try {
      const token = location.pathname.split('/').pop();
      const prefix = form.dataset.prefix || '';
      const payload = await encryptPayload(form.dataset.publicKey, value);
      textarea.value = '';
      const response = await fetch(`${prefix}/api/drop/${encodeURIComponent(token)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('closed');
      document.querySelector('.panel-inner').innerHTML = '<div class="state"><h1>Saved securely. This link is now closed.</h1></div>';
    } catch (_) {
      document.querySelector('.panel-inner').innerHTML = '<div class="state"><h1>This link is closed.</h1></div>';
    }
  });
}
