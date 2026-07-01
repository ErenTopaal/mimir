"use client"

import { useEffect, useState } from "react"
import { AppHeader } from "@/components/app-header"
import { API_BASE } from "@/lib/api"

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

interface DashboardData {
  stats: DashboardStats
  trending: TrendingContract[]
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const chain = "avalanche"

  useEffect(() => {
    fetch(`${API_BASE}/v1/dashboard/${chain}`)
      .then((r) => r.json())
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load dashboard data")
      })
      .finally(() => setLoading(false))
  }, [chain])

  return (
    <div className="min-h-screen bg-background">
      <AppHeader />
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-2">Avalanche Security Dashboard</h1>
        <p className="text-muted-foreground mb-8">
          Ecosystem-wide security scan results for Avalanche smart contracts.
        </p>

        {loading && <p className="text-muted-foreground">Loading...</p>}

        {error && (
          <p className="text-red-600 text-sm mb-4">{error}</p>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              {[
                { label: "Contracts scanned", value: data.stats.total_scanned },
                { label: "Last 24h", value: data.stats.scanned_last_24h },
                { label: "Total findings", value: data.stats.total_findings },
                { label: "High severity", value: data.stats.high_severity },
              ].map((s) => (
                <div key={s.label} className="border rounded-lg p-4">
                  <div className="text-2xl font-bold">{s.value}</div>
                  <div className="text-sm text-muted-foreground">{s.label}</div>
                </div>
              ))}
            </div>

            <h2 className="text-lg font-semibold mb-4">Recent scans</h2>
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left p-3 font-medium">Address</th>
                    <th className="text-left p-3 font-medium">High findings</th>
                    <th className="text-left p-3 font-medium">Scanned</th>
                    <th className="text-left p-3 font-medium">Report</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trending.map((c) => (
                    <tr key={c.job_id} className="border-t">
                      <td className="p-3 font-mono text-xs">
                        {c.address.slice(0, 10)}...{c.address.slice(-8)}
                      </td>
                      <td className="p-3">
                        <span
                          className={
                            c.high_findings > 0
                              ? "text-red-600 font-semibold"
                              : "text-green-600"
                          }
                        >
                          {c.high_findings}
                        </span>
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(c.created_at).toLocaleDateString()}
                      </td>
                      <td className="p-3">
                        <a
                          href={`/results?job_id=${c.job_id}`}
                          className="text-primary underline"
                        >
                          View
                        </a>
                      </td>
                    </tr>
                  ))}
                  {data.trending.length === 0 && (
                    <tr>
                      <td colSpan={4} className="p-6 text-center text-muted-foreground">
                        No contracts scanned yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
