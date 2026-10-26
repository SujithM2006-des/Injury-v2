import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Role } from './types'
import { login as loginSvc } from './api/services'
import { devMode, sessionKeyStore, setUnauthorizedHandler, tokenStore } from './api/client'
import { toRole } from './api/mappers'

export interface User { name: string; role: Role; teamId: number | null; dev?: boolean }
interface Ctx { user: User | null; login: (u: string, p: string) => Promise<User>; devPreview: (r: Role) => void; logout: () => void }

const C = createContext<Ctx>(null as unknown as Ctx)
export const useAuth = () => useContext(C)
export const home: Record<Role, string> = { ADMIN: '/admin/dashboard', COACH: '/coach/dashboard', MEDICAL: '/medical/dashboard', PLAYER: '/player/dashboard', OWNER: '/owner/dashboard' }

const USER_KEY = 'athleteguard_user'

function savedUser(): User | null {
  try {
    if (!tokenStore.get()) return null
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(savedUser)
  const qc = useQueryClient()

  // Drop everything loaded for the previous account, so a new login never sees its cached lists
  // (e.g. a player's own one-player list showing as "Total players: 1" on the admin dashboard).
  const logout = useCallback(() => {
    qc.clear()
    tokenStore.clear()
    sessionKeyStore.clear()
    localStorage.removeItem(USER_KEY)
    devMode.set(false)
    setUser(null)
  }, [qc])

  // Session expired -> log out (Layout then redirects to /login)
  useEffect(() => { setUnauthorizedHandler(logout) }, [logout])

  const login = async (u: string, p: string) => {
    const r = await loginSvc(u, p)
    qc.clear()
    tokenStore.set(r.access_token)
    sessionKeyStore.set(r.session_key)
    devMode.set(false)
    const next: User = { name: r.username, role: toRole(r.role), teamId: r.team_id }
    localStorage.setItem(USER_KEY, JSON.stringify(next))
    setUser(next)
    return next
  }

  /** Look at each role's screens without logging in (no data is loaded). */
  const devPreview = (role: Role) => {
    qc.clear()
    tokenStore.clear()
    sessionKeyStore.clear()
    localStorage.removeItem(USER_KEY)
    devMode.set(true)
    setUser({ name: `Preview ${role.toLowerCase()}`, role, teamId: null, dev: true })
  }

  return <C.Provider value={{ user, login, devPreview, logout }}>{children}</C.Provider>
}