// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-generated window event that tells the errand lists and the credit banner to reload after a change.
// Author review: <to be completed by author>

const ERRANDS_CHANGED = 'campusrun:errands-changed'

// Sent after any errand action, create or edit, including ones the server refused (409), since then the
// errand has changed under the user
export function notifyErrandsChanged() {
  window.dispatchEvent(new Event(ERRANDS_CHANGED))
}

export function onErrandsChanged(listener: () => void) {
  window.addEventListener(ERRANDS_CHANGED, listener)
  return () => window.removeEventListener(ERRANDS_CHANGED, listener)
}
