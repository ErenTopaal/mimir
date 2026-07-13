"use client"

import { useRouter } from "next/navigation"
import type { RecentJob } from "@/lib/recent-jobs"

interface RecentRunsProps {
  jobs: RecentJob[]
  onClear: () => void
}

export function RecentRuns({ jobs, onClear }: RecentRunsProps) {
  const router = useRouter()

  if (jobs.length === 0) return null

  return (
    <div className="border-t pt-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-muted-foreground">
          Recent runs
        </span>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Clear
        </button>
      </div>
      <div className="mt-2 space-y-0.5">
        {jobs.slice(0, 6).map((job) => (
          <button
            key={job.job_id}
            type="button"
            onClick={() => router.push(`/results?job_id=${job.job_id}`)}
            className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted/40"
            title={job.job_id}
          >
            <span className="min-w-0 flex-1 truncate text-foreground">
              {job.label}
            </span>
            <span className="shrink-0 font-mono text-muted-foreground">
              {job.job_id.slice(0, 8)}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
