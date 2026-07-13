import { cn } from "@/lib/utils"

interface SpinnerProps extends React.ComponentProps<"span"> {
  size?: "sm" | "md"
}

function Spinner({ className, size = "sm", ...props }: SpinnerProps) {
  return (
    <span
      data-slot="spinner"
      className={cn(
        "inline-block animate-spin rounded-full border-2 border-current border-t-transparent",
        size === "sm" && "size-3.5",
        size === "md" && "size-4",
        className,
      )}
      aria-hidden="true"
      {...props}
    />
  )
}

export { Spinner }
