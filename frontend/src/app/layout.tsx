import type { Metadata } from "next"
import { GeistMono } from "geist/font/mono"
import { GeistSans } from "geist/font/sans"
import { NuqsAdapter } from "nuqs/adapters/next/app"
import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import "@/styles/globals.css"

export const metadata: Metadata = {
  title: "AvaxBench",
  description: "Avalanche smart contract vulnerability detection",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={cn(GeistSans.variable, GeistMono.variable, "antialiased")}
      suppressHydrationWarning
    >
      <body className="font-sans antialiased">
        <NuqsAdapter>
          <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem
            disableTransitionOnChange
          >
            <TooltipProvider>
              {children}
              <Toaster />
            </TooltipProvider>
          </ThemeProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}
