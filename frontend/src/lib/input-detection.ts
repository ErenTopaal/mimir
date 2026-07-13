export type InputType = "address" | "github" | "unknown"

const ADDR_RE = /^0x[a-fA-F0-9]{40}$/

export function detectInputType(value: string): InputType {
  const s = value.trim()
  if (ADDR_RE.test(s)) return "address"
  if (s.includes("github.com")) return "github"
  return "unknown"
}
