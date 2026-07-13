"use client"

import { cn } from "@/lib/utils"

interface AppFooterProps {
  className?: string
  showBorder?: boolean
}

export function AppFooter({ className, showBorder = true }: AppFooterProps) {
  return (
    <footer
      className={cn(
        "flex shrink-0 flex-col items-center gap-x-2 p-3 text-xs text-muted-foreground sm:flex-row sm:justify-between sm:py-0",
        showBorder ? "sm:h-8 border-t" : "sm:h-10",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-center gap-x-3">
        <span className="text-xs">
          &copy; {new Date().getFullYear()} AvaxBench
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs">Avalanche smart contract security</span>
      </div>
    </footer>
  )
}
