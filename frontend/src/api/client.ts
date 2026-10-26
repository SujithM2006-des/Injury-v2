import axios, { AxiosError } from 'axios'

// Backend address. Defaults to the local FastAPI server; override with VITE_API_BASE_URL in .env.
const envBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()
export const API_BASE = envBase ? envBase.replace(/\/$/, '') : 'http://127.0.0.1:8000'
export const isConnected = true

// Token + user are kept in localStorage so a page refresh keeps you logged in.
const TOKEN_KEY = 'access_token'
export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

/* ---------- end-to-end encryption (backend/secure_transport.py) ----------
 * The login gives a per-session AES-256 key. Every JSON response for a logged-in user arrives as
 * {"__ag_enc": base64(12-byte nonce + ciphertext + tag)} and is decrypted here; JSON request bodies
 * are encrypted the same way (header X-AG-Enc: 1). Uses the browser's Web Crypto (needs https or localhost). */
const SESSION_KEY = 'session_key'
const ENC_FIELD = '__ag_enc'
export const sessionKeyStore = {
  get: () => localStorage.getItem(SESSION_KEY),
  set: (k: string) => localStorage.setItem(SESSION_KEY, k),
  clear: () => localStorage.removeItem(SESSION_KEY),
}

const b64ToBytes = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
const bytesToB64 = (b: Uint8Array) => { let s = ''; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000)); return btoa(s) }

let cachedKey: { raw: string; key: CryptoKey } | null = null
async function aesKey(): Promise<CryptoKey | null> {
  const raw = sessionKeyStore.get()
  if (!raw || !globalThis.crypto?.subtle) return null
  if (cachedKey?.raw !== raw) cachedKey = { raw, key: await crypto.subtle.importKey('raw', b64ToBytes(raw), 'AES-GCM', false, ['encrypt', 'decrypt']) }
  return cachedKey.key
}

const isEncrypted = (d: unknown): d is Record<typeof ENC_FIELD, string> =>
  !!d && typeof d === 'object' && typeof (d as Record<string, unknown>)[ENC_FIELD] === 'string'

async function decryptPayload(text: string): Promise<unknown> {
  const key = await aesKey()
  if (!key) throw new Error('missing session key')
  const b = b64ToBytes(text)
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b.subarray(0, 12) }, key, b.subarray(12))
  return JSON.parse(new TextDecoder().decode(plain))
}

async function encryptPayload(data: unknown): Promise<string | null> {
  const key = await aesKey()
  if (!key) return null
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(JSON.stringify(data))))
  const out = new Uint8Array(12 + ct.length)
  out.set(iv); out.set(ct, 12)
  return bytesToB64(out)
}

// Developer preview (no login, no data): API calls are switched off.
let dev = false
export const devMode = { get: () => dev, set: (v: boolean) => { dev = v } }

export const api = axios.create({ baseURL: API_BASE, timeout: 15000 })

api.interceptors.request.use(async (c) => {
  const t = tokenStore.get()
  if (t) {
    c.headers.Authorization = `Bearer ${t}`
    // JSON bodies of a logged-in user are sent encrypted
    if (c.data !== undefined && !(c.data instanceof FormData) && !(c.data instanceof Blob)) {
      const enc = await encryptPayload(c.data)
      if (enc) { c.data = { [ENC_FIELD]: enc }; c.headers['X-AG-Enc'] = '1' }
    }
  }
  return c
})

// Expired or invalid session (tokens last 8 hours) -> back to the login page
let onUnauthorized: (() => void) | null = null
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn }

api.interceptors.response.use(
  async (r) => {
    if (isEncrypted(r.data)) {
      try { r.data = await decryptPayload(r.data[ENC_FIELD]) } catch {
        // key missing or from an older login: start a fresh session
        onUnauthorized?.()
        throw new Error('Your session expired. Please log in again.')
      }
    }
    return r
  },
  async (e: AxiosError) => {
    if (e.response && isEncrypted(e.response.data)) {
      try { e.response.data = await decryptPayload(e.response.data[ENC_FIELD]) } catch { /* keep the raw error */ }
    }
    const isLogin = e.config?.url?.includes('/auth/login')
    if (e.response?.status === 401 && !isLogin && onUnauthorized) onUnauthorized()
    return Promise.reject(e)
  },
)

export function normalizeApiError(e: unknown): string {
  if (!(e instanceof AxiosError)) return e instanceof Error ? e.message : 'Something went wrong.'
  if (!e.response) return `Can't reach the backend at ${API_BASE}. Is it running?`
  const s = e.response.status
  const d = (e.response.data as { detail?: unknown })?.detail
  if (typeof d === 'string' && s !== 401) return d
  if (s === 401) return e.config?.url?.includes('/auth/login') ? 'Invalid username or password.' : 'Your session has expired. Please log in again.'
  if (s === 403) return 'You are not authorized to do this.'
  if (s === 404) return 'The requested resource was not found.'
  if (s === 422) return 'Some fields are invalid.'
  if (s >= 500) return 'Something went wrong on the server. Please try again.'
  return 'Request failed.'
}