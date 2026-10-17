// AI Assistance Disclosure:
// Tool: OpenAI Codex (GPT-6), date: 2026-10-17
// Scope: Moved the order autofill response type into the shared types module.
// Author review: <to be completed by author>

export type AutofillSuggestion = {
  title: string | null
  supplier: { id: number; name: string } | null
  building: string | null
  floor: string | null
  description: string | null
  deliveryBy: string | null
  credits: number | null
}
