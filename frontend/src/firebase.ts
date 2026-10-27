// "Sign in with Google" through Firebase Authentication.
// The browser gets a Firebase ID token for the chosen Google account; the backend (POST /auth/firebase)
// checks it and logs the person in with the role the admin assigned to that Gmail.
// We keep no Firebase session: Firebase is signed out again right after the token is made.
//
// Two ways to open the Google window:
//  1. VITE_GOOGLE_CLIENT_ID set (preferred): Google's own account picker on accounts.google.com
//     (Google Identity Services). The Google sign-in is then turned into a Firebase token through
//     googleapis.com. Nothing is loaded from <project>.firebaseapp.com, which some networks
//     (e.g. some ISPs / college Wi-Fi in India) block.
//  2. Otherwise: Firebase's own pop-up, which runs on <project>.firebaseapp.com.
// Config: VITE_FIREBASE_* and VITE_GOOGLE_CLIENT_ID in frontend/.env.
import { initializeApp, type FirebaseApp } from 'firebase/app'
import { GoogleAuthProvider, getAuth, inMemoryPersistence, initializeAuth, signInWithCredential, signInWithPopup, signOut, type Auth } from 'firebase/auth'

const env = import.meta.env
const config = {
  apiKey: (env.VITE_FIREBASE_API_KEY as string | undefined)?.trim(),
  authDomain: (env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined)?.trim(),
  projectId: (env.VITE_FIREBASE_PROJECT_ID as string | undefined)?.trim(),
  appId: (env.VITE_FIREBASE_APP_ID as string | undefined)?.trim(),
}
const googleClientId = (env.VITE_GOOGLE_CLIENT_ID as string | undefined)?.trim()

/** False until the Firebase web config is in frontend/.env */
export const firebaseReady = !!(config.apiKey && config.authDomain && config.projectId)

let app: FirebaseApp | null = null
let auth: Auth | null = null

function firebaseAuth(): Auth {
  app ??= initializeApp(config)
  // without the pop-up helper, Firebase never contacts <project>.firebaseapp.com
  auth ??= googleClientId ? initializeAuth(app, { persistence: inMemoryPersistence }) : getAuth(app)
  return auth
}

/* ---------- 1. Google Identity Services (accounts.google.com) ---------- */

type TokenResponse = { access_token?: string; error?: string; error_description?: string }
type GoogleOAuth = { accounts: { oauth2: { initTokenClient: (o: { client_id: string; scope: string; prompt?: string; callback: (r: TokenResponse) => void; error_callback?: (e: { type?: string }) => void }) => { requestAccessToken: () => void } } } }

let gisScript: Promise<void> | null = null
function loadGis(): Promise<void> {
  gisScript ??= new Promise<void>((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => { gisScript = null; reject(new Error('Could not reach accounts.google.com. Check the internet connection.')) }
    document.head.appendChild(s)
  })
  return gisScript
}

/** Opens Google's account picker; resolves with a Google access token. */
async function googleAccessToken(): Promise<string> {
  await loadGis()
  const google = (window as unknown as { google?: GoogleOAuth }).google
  if (!google?.accounts?.oauth2) throw new Error('Google sign-in did not load. Please try again.')
  return new Promise<string>((resolve, reject) => {
    const client = google.accounts.oauth2.initTokenClient({
      client_id: googleClientId!,
      scope: 'openid email profile',
      prompt: 'select_account',
      callback: (r) => (r.access_token ? resolve(r.access_token) : reject(new Error(r.error === 'access_denied' ? 'Sign-in was cancelled.' : r.error_description || 'Google sign-in failed. Please try again.'))),
      error_callback: (e) => reject(new Error(e?.type === 'popup_closed' ? 'Sign-in was cancelled.' : e?.type === 'popup_failed_to_open' ? 'The browser blocked the Google window. Allow pop-ups for this site and try again.' : 'Google sign-in failed. Please try again.')),
    })
    client.requestAccessToken()
  })
}

/* ---------- the token for the backend ---------- */

/** Opens the Google account picker; returns the Firebase ID token for the backend. */
export async function googleIdToken(): Promise<string> {
  if (!firebaseReady) throw new Error('Google sign-in is not set up yet. Add the Firebase config to frontend/.env.')
  const a = firebaseAuth()
  try {
    if (googleClientId) {
      const accessToken = await googleAccessToken()
      const result = await signInWithCredential(a, GoogleAuthProvider.credential(null, accessToken))
      return await result.user.getIdToken()
    }
    const provider = new GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    const result = await signInWithPopup(a, provider)
    return await result.user.getIdToken()
  } catch (e) {
    const code = (e as { code?: string }).code ?? ''
    if (!code && e instanceof Error) throw e
    if (code === 'auth/popup-closed-by-user' || code === 'auth/cancelled-popup-request') throw new Error('Sign-in was cancelled.')
    if (code === 'auth/popup-blocked') throw new Error('The browser blocked the Google window. Allow pop-ups for this site and try again.')
    if (code === 'auth/unauthorized-domain') throw new Error('This address is not allowed in Firebase. Add it under Authentication -> Settings -> Authorized domains.')
    if (code === 'auth/operation-not-allowed') throw new Error('Google sign-in is turned off in Firebase. Enable it under Authentication -> Sign-in method.')
    if (code === 'auth/invalid-credential') throw new Error('Google sign-in could not be confirmed by Firebase. Check that the Web client ID belongs to this Firebase project.')
    if (code === 'auth/network-request-failed') throw new Error('Firebase could not be reached from this network. Try another network (e.g. a mobile hotspot).')
    throw new Error('Google sign-in failed. Please try again.')
  } finally {
    signOut(a).catch(() => undefined)
  }
}
