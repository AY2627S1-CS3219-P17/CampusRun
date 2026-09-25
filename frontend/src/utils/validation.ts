export function validateUsername(username: string): string {
  return /^[A-Za-z0-9_-]{3,}$/.test(username)
    ? ''
    : 'Use 3+ characters: letters, numbers, underscores or hyphens only.'
}

export function validatePassword(password: string): string {
  return password.length >= 8 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /[0-9]/.test(password) &&
    /[^A-Za-z0-9\s]/.test(password)
    ? ''
    : 'Use 8+ characters with uppercase, lowercase, a number and a special character.'
}
export function validateEmail(email: string): string {
  return /^[^\s@]+@u\.nus\.edu$/i.test(email.trim())
    ? ''
    : 'Enter a valid @u.nus.edu email.'
}

export function validateConfirmPassword(
  password: string,
  confirmPassword: string,
): string {
  if (!confirmPassword) return 'Confirm your password.'
  return password !== confirmPassword ? 'Passwords do not match.' : ''
}
