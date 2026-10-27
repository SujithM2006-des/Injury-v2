import { type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, home, useAuth } from './auth'
import { ToastProvider } from './ui'
import Layout from './Layout'
import type { Role } from './types'
import * as P from './pages'
import * as PL from './playerPages'

const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })
const G = ({ roles, children }: { roles: Role[]; children: ReactNode }) => {
  const { user } = useAuth()
  return user && roles.includes(user.role) ? <>{children}</> : <P.ErrorPage kind="403" />
}
const RoleHome = () => {
  const { user } = useAuth()
  return user ? <Navigate to={home[user.role]} replace /> : <Navigate to="/login" replace />
}
const ALL: Role[] = ['ADMIN', 'MEDICAL', 'COACH', 'OWNER']

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <ToastProvider>
            <Routes>
              <Route path="/login" element={<P.Login />} />
              <Route element={<Layout />}>
                <Route index element={<RoleHome />} />
                <Route path="/admin/dashboard" element={<G roles={['ADMIN']}><P.Dashboard role="ADMIN" /></G>} />
                <Route path="/coach/dashboard" element={<G roles={['COACH']}><P.Dashboard role="COACH" /></G>} />
                <Route path="/medical/dashboard" element={<G roles={['MEDICAL']}><P.Dashboard role="MEDICAL" /></G>} />
                <Route path="/owner/dashboard" element={<G roles={['OWNER']}><P.Dashboard role="OWNER" /></G>} />
                <Route path="/live" element={<G roles={[...ALL, 'PLAYER']}><P.WatchLive /></G>} />
                <Route path="/teams" element={<G roles={ALL}><P.ListPage k="teams" /></G>} />
                <Route path="/teams/:id" element={<G roles={ALL}><P.Detail k="teams" /></G>} />
                <Route path="/players" element={<G roles={ALL}><P.ListPage k="players" /></G>} />
                <Route path="/players/:id" element={<G roles={ALL}><P.Detail k="players" /></G>} />
                <Route path="/matches" element={<G roles={ALL}><P.ListPage k="matches" /></G>} />
                <Route path="/matches/:id" element={<G roles={ALL}><P.MatchDetail /></G>} />
                <Route path="/matches/:id/monitor" element={<G roles={ALL}><P.Monitor /></G>} />
                <Route path="/events" element={<G roles={ALL}><P.ListPage k="events" /></G>} />
                <Route path="/events/:id" element={<G roles={[...ALL, 'PLAYER']}><P.EventDetail /></G>} />
                {/* Player logins: their own dashboard, profile, injury history, current injury events and report */}
                <Route path="/player/dashboard" element={<G roles={['PLAYER']}><PL.PlayerDashboard /></G>} />
                <Route path="/player/profile" element={<G roles={['PLAYER']}><PL.PlayerProfile /></G>} />
                <Route path="/player/history" element={<G roles={['PLAYER']}><PL.PlayerHistoryPage /></G>} />
                <Route path="/player/events" element={<G roles={['PLAYER']}><PL.PlayerEvents /></G>} />
                <Route path="/player/reports" element={<G roles={['PLAYER']}><PL.PlayerReports /></G>} />
                <Route path="/events/:id/assessment" element={<G roles={['MEDICAL']}><P.Assessment /></G>} />
                <Route path="/collisions" element={<G roles={ALL}><P.ListPage k="collisions" /></G>} />
                <Route path="/collisions/:id" element={<G roles={ALL}><P.EventDetail collision /></G>} />
                <Route path="/alerts" element={<G roles={ALL}><P.Alerts /></G>} />
                <Route path="/reports" element={<G roles={ALL}><P.ListPage k="reports" /></G>} />
                <Route path="/reports/:id" element={<Navigate to="/reports" replace />} />
                <Route path="/admin/users" element={<G roles={['ADMIN', 'OWNER']}><P.ListPage k="users" /></G>} />
                <Route path="/admin/system" element={<G roles={['ADMIN', 'OWNER']}><P.System /></G>} />
                <Route path="/settings" element={<P.Settings />} />
                <Route path="/help" element={<P.Help />} />
                <Route path="/offline" element={<P.ErrorPage kind="network" />} />
                <Route path="/error" element={<P.ErrorPage kind="generic" />} />
                <Route path="*" element={<P.ErrorPage kind="404" />} />
              </Route>
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}