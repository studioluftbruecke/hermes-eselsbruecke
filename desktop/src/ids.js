// UUIDs from crypto.getRandomValues: the outbox's op ids and the generator. No imports, so the parity
// test can load it in node.

/** RFC 9562 UUID v7 from crypto.getRandomValues (the outbox's op ids, and the generator). */
export function uuid7(ms = Date.now()) {
  const b = new Uint8Array(16)
  crypto.getRandomValues(b)
  let t = ms
  for (let i = 5; i >= 0; i--) {
    b[i] = t % 256
    t = Math.floor(t / 256)
  }
  b[6] = (b[6] & 0x0f) | 0x70
  b[8] = (b[8] & 0x3f) | 0x80
  return hexUuid(b)
}

export function uuid4() {
  const b = new Uint8Array(16)
  crypto.getRandomValues(b)
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  return hexUuid(b)
}

function hexUuid(b) {
  const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
