// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-28
// Scope: AI-added StudentRoute, which keeps admins out of the errand pages; AI-removed it again, since admins
//        keep every student capability (2026-09-28).
// Tool: OpenAI Codex (GPT-6), date: 2026-10-20
// Scope: Kept the main navigation header mounted across the three errand routes.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
// Scope: AI-added the admin page and AdminRoute, which sends non-admins to Explore.
// Author review: I tested the behaviour: non-admins visiting the admin page are sent to Explore.

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, Outlet } from 'react-router'
import Login from './pages/auth/login.tsx'
import Register from './pages/auth/register.tsx'
import Explore from './pages/main/explore.tsx'
import MyTasks from './pages/main/my-tasks.tsx'
import MyRequests from './pages/main/my-requests.tsx'
import Suppliers from './pages/header/suppliers.tsx'
import Admin from './pages/header/admin.tsx'
import Header from './components/shared/header.tsx'
import './pages/main/explore.css'
import { useSession } from './utils/session'

export default function ProtectedRoute() {
  return useSession() ? <Outlet /> : <Navigate to="/login" replace />
}

// The admin services make the real check (403); this only keeps students off a page they can't use
function AdminRoute() {
  return useSession()?.role === 'admin' ? (
    <Outlet />
  ) : (
    <Navigate to="/explore" replace />
  )
}

function MainLayout() {
  return (
    <div className="explore-page">
      <Header />
      <Outlet />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<MainLayout />}>
            <Route path="/explore" element={<Explore />} />
            <Route path="/my-tasks" element={<MyTasks />} />
            <Route path="/my-requests" element={<MyRequests />} />
          </Route>
          <Route path="/suppliers" element={<Suppliers />} />
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<Admin />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
