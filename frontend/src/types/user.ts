// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-added the User type and changed UpdateUserPayload to match the User Service's PATCH /users/me;
//        AI-added the role (2026-09-28).
// Author review: Validated types against the User Service contract.

// Admins are users with the admin role; they can't post or accept errands
export type Role = 'student' | 'admin'

export type RegisterUserValues = {
  username: string
  email: string
  password: string
  confirmPassword: string
}

export type RegisterUserPayload = Omit<RegisterUserValues, 'confirmPassword'>
export type LoginUserPayload = Omit<RegisterUserPayload, 'username'>

// Only changed fields are submitted (new password requires current password)
export type UpdateUserPayload = {
  username?: string
  current_password?: string
  new_password?: string
}

// Field names follow the User Service's JSON, which is snake_case
export type User = {
  id: number
  email: string
  username: string
  email_verified_at: string | null
  role: Role
  created_at: string
}
