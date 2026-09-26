// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-added the User type and changed UpdateUserPayload to match the User Service's PATCH /users/me.
// Author review: <to be completed by author>

export type RegisterUserValues = {
  username: string
  email: string
  password: string
  confirmPassword: string
}

export type RegisterUserPayload = Omit<RegisterUserValues, 'confirmPassword'>
export type LoginUserPayload = Omit<RegisterUserPayload, 'username'>

// Field names follow the User Service's JSON, which is snake_case
export type User = {
  id: number
  email: string
  username: string
  email_verified_at: string | null
  created_at: string
}

// Omitted fields are left unchanged; new_password needs current_password
export type UpdateUserPayload = {
  username?: string
  current_password?: string
  new_password?: string
}
