"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { AppFooter } from "@/components/app-footer"
import { AppHeader } from "@/components/app-header"
import { Spinner } from "@/components/ui/spinner"
import { API_BASE } from "@/lib/api"
import { cn } from "@/lib/utils"

interface DashboardStats {
  total_scanned: number
  total_findings: number
  high_severity: number
  scanned_last_24h: number
}

interface TrendingContract {
  address: string
  chain: string
  job_id: string
  high_findings: number
  created_at: string
}

interface VulnPattern {
  title: string
  count: number
  percentage: number
}

interface DashboardData {
  stats: DashboardStats
  trending: TrendingContract[]
  patterns: VulnPattern[]
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/v1/dashboard/avalanche`)
      .then((r) => r.json())
      .then(setData)
      .catch((err: unknown) => {
        setError(
          err instanceof Error ? err.message : "Failed to load dashboard data",
        )
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="flex min-h-screen w-screen flex-col">
      <AppHeader showLogo />
      <section className="flex flex-1 justify-center px-6 py-10">
        <div className="w-full max-w-3xl">
          <h1 className="text-2xl font-semibold mb-2">
            Avalanche Security Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mb-8">
            Ecosystem-wide security scan results for Avalanche smart contracts.
          </p>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {loading && (
            <div className="flex items-center gap-2 py-12 justify-center text-sm text-muted-foreground">
              <Spinner size="sm" />
              <span>Loading dashboard...</span>
            </div>
          )}

          {data && (
            <>
              <div className="grid grid-cols-2 gap-4 mb-10 animate-fade-in">
                {[
                  {
                    label: "Contracts scanned",
                    value: data.stats.total_scanned,
                  },
                  { label: "Last 24h", value: data.stats.scanned_last_24h },
                  { label: "Total findings", value: data.stats.total_findings },
                  {
                    label: "High severity",
                    value: data.stats.high_severity,
                    highlight: true,
                  },
                ].map((s) => (
                  <div
                    key={s.label}
                    className="border rounded-lg p-6 transition-colors hover:bg-muted/30"
                  >
                    <div
                      className={cn(
                        "text-2xl font-mono font-semibold",
                        "highlight" in s &&
                          s.highlight &&
                          s.value > 0 &&
                          "text-severity-high-foreground",
                      )}
                    >
                      {s.value.toLocaleString()}
                    </div>
                    <div className="text-sm text-muted-foreground mt-1">
                      {s.label}
                    </div>
                  </div>
                ))}
              </div>

              <div
                className="mb-10 animate-fade-in"
                style={{ animationDelay: "80ms" }}
              >
                <h2 className="text-lg font-semibold mb-4">Recent scans</h2>
                <div className="space-y-1">
                  {data.trending.map((c) => (
                    <Link
                      key={c.job_id}
                      href={`/results?job_id=${c.job_id}`}
                      className="flex flex-col gap-1 border rounded-md px-4 py-3 hover:bg-muted/40 transition-colors border-l-2 border-l-transparent hover:border-l-primary/50 md:grid md:grid-cols-[minmax(0,1fr)_100px_140px_80px] md:items-center md:gap-x-6"
                    >
                      <span className="truncate font-mono text-xs">
                        {c.address.slice(0, 10)}...{c.address.slice(-8)}
                      </span>
                      <span
                        className={cn(
                          "text-xs",
                          c.high_findings > 0
                            ? "font-medium text-severity-high-foreground"
                            : "text-severity-low-foreground",
                        )}
                      >
                        {c.high_findings} high
                      </span>
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {new Date(c.created_at).toLocaleDateString()}
                      </span>
                      <span className="text-xs text-primary">View</span>
                    </Link>
                  ))}
                  {data.trending.length === 0 && (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No contracts scanned yet.
                    </p>
                  )}
                </div>
              </div>

              {data.patterns && data.patterns.length > 0 && (
                <div
                  className="animate-fade-in"
                  style={{ animationDelay: "160ms" }}
                >
                  <h2 className="text-lg font-semibold mb-4">
                    Most common vulnerability patterns
                  </h2>
                  <div className="space-y-2">
                    {data.patterns.map((p) => (
                      <div key={p.title} className="space-y-1">
                        <div className="flex items-baseline justify-between gap-4">
                          <span className="min-w-0 truncate text-xs text-foreground capitalize">
                            {p.title}
                          </span>
                          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                            {p.percentage.toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-muted">
                          <div
                            className="h-1.5 rounded-full bg-primary/40"
                            style={{ width: `${Math.min(p.percentage, 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </section>
      <AppFooter />
    </main>
  )
}
