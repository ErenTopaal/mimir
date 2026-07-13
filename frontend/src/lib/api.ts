// Runtime detection for reverse proxy setups (e.g., /avaxbench)
export const PATH_PREFIX =
  typeof window !== "undefined" &&
  window.location.pathname.startsWith("/avaxbench")
    ? "/avaxbench"
    : ""

export const API_BASE = PATH_PREFIX
  ? `${PATH_PREFIX}/api`
  : (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:50337")
