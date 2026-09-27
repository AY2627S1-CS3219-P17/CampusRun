import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, Outlet } from 'react-router'
import Login from './pages/login.tsx'
import Register from './pages/register.tsx'
import Explore from './pages/explore.tsx'
import MyTasks from './pages/my-tasks.tsx'
import MyRequests from './pages/my-requests.tsx'
import Suppliers from './pages/suppliers.tsx'
import { useSession } from './utils/session'

export default function ProtectedRoute() {
  return useSession() ? <Outlet /> : <Navigate to="/login" replace />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/explore" element={<Explore />} />
          <Route path="/my-tasks" element={<MyTasks />} />
          <Route path="/my-requests" element={<MyRequests />} />
          <Route path="/suppliers" element={<Suppliers />} />
        </Route>

        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
