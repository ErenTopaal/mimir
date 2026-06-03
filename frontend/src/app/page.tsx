"use client"

import { useRouter } from "next/navigation"
import { useCallback, useMemo, useRef, useState } from "react"
import { AppFooter } from "@/components/app-footer"
import { AppHeader } from "@/components/app-header"
import { FileUploader } from "@/components/file-uploader"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/hooks/use-auth"
import { useLocalStorage } from "@/hooks/use-local-storage"
import { useSessionStorage } from "@/hooks/use-session-storage"
import { API_BASE } from "@/lib/api"
import { startJob } from "@/lib/jobs"
import { addRecentJob, type RecentJob } from "@/lib/recent-jobs"
import { inferPackageName } from "@/lib/upload-utils"
import { createZipFromFiles } from "@/lib/zip"
import { useUploadStore } from "@/store/upload-store"

const AVALANCHE_ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/

export default function Page() {
  const router = useRouter()
  const { files, packageName, setUpload, clearUpload } = useUploadStore()
  const [openaiKey, setOpenaiKey] = useSessionStorage("avaxbench.openaiKey", "")
  const [model, setModel] = useState("codex-gpt-5.2")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [recentJobs, setRecentJobs] = useLocalStorage<RecentJob[]>(
    "avaxbench.recentJobs.v1",
    [],
  )
  const [universalInput, setUniversalInput] = useState("")
  const [universalNotice, setUniversalNotice] = useState<string | null>(null)
  const fileUploaderRef = useRef<HTMLDivElement>(null)
  const {
    isAuthorized,
    isLoading: isAuthLoading,
    isConfigLoading,
    keyPredefined,
  } = useAuth()

  const fileCount = files?.length ?? 0
  const selectedLabel = useMemo(() => {
    if (packageName) return packageName
    if (files) return inferPackageName(files)
    return null
  }, [files, packageName])

  const canSubmit =
    !!files && fileCount > 0 && !isSubmitting && !isAuthLoading && isAuthorized

  const handleFilesSelected = useCallback(
    (selected: File[]) => {
      setUpload(selected, inferPackageName(selected))
    },
    [setUpload],
  )

  const handleKeyChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      setOpenaiKey(event.target.value)
    },
    [setOpenaiKey],
  )

  const handleUniversalInput = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key !== "Enter") return
      const value = universalInput.trim()
      if (!value) return
      setUniversalNotice(null)
      if (AVALANCHE_ADDRESS_RE.test(value)) {
        router.push(`/results?chain=avalanche&address=${value}`)
        return
      }
      if (value.includes("github.com")) {
        setUniversalNotice("GitHub URL auditing coming soon.")
        return
      }
      // Focus file uploader for any other input
      fileUploaderRef.current?.querySelector("input")?.focus()
    },
    [universalInput, router],
  )

  const handleSubmit = async () => {
    if (!files || fileCount === 0) return
    if (!isAuthorized) {
      setSubmitError("Authorize with GitHub to start analysis.")
      return
    }
    const trimmedKey = openaiKey.trim()

    setIsSubmitting(true)
    setSubmitError(null)

    try {
      const name = selectedLabel ?? "files"
      const zipFile = await createZipFromFiles(files, name)
      const response = await startJob(zipFile, model, trimmedKey)
      // Persist locally so users can navigate back without server-side auth/history.
      const next = addRecentJob({
        job_id: response.job_id,
        label: name,
        created_at_ms: Date.now(),
      })
      setRecentJobs(next)
      router.push(`/results?job_id=${response.job_id}`)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Upload failed")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen w-screen flex-col">
      <AppHeader showLogo={false} showBorder={false} />
      <section className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-4xl">
          <div className="mx-auto grid max-w-sm gap-10 lg:max-w-none lg:grid-cols-5">
            <div className="space-y-6 lg:col-span-3">
              <div>
                <h1 className="text-5xl leading-[1.1] font-serif text-foreground mb-1.5">
                  AvaxBench
                </h1>
                <h2 className="text-2xl leading-[1.1] font-serif text-foreground mb-3">
                  Evaluating AI performance on Avalanche smart contract findings
                </h2>
                <div className="space-y-2 text-base text-foreground/80">
                  <p className="leading-tight">
                    AvaxBench is a benchmark that evaluates whether AI agents
                    can detect, patch, and exploit high-severity vulnerabilities
                    in Avalanche smart contracts.
                  </p>
                  <p className="leading-tight">
                    This interface focuses on detection and only reports
                    high-severity findings. Upload a contract folder, provide an
                    API key, and start a run.
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-6 lg:col-span-2">
              <div className="grid gap-1">
                <Label htmlFor="universal-input" className="text-xs text-foreground">
                  Address or GitHub URL
                </Label>
                <Input
                  id="universal-input"
                  type="text"
                  placeholder="0x… address or github.com/…"
                  value={universalInput}
                  onChange={(e) => {
                    setUniversalInput(e.target.value)
                    setUniversalNotice(null)
                  }}
                  onKeyDown={handleUniversalInput}
                />
                {universalNotice && (
                  <p className="text-xs text-muted-foreground">{universalNotice}</p>
                )}
              </div>

              <div ref={fileUploaderRef}>
                <FileUploader
                  onFilesSelected={handleFilesSelected}
                  files={files}
                  selectedLabel={selectedLabel}
                  fileCount={fileCount}
                  disabled={isSubmitting}
                  onClear={clearUpload}
                />
              </div>

              <div className="grid gap-3 text-xs text-muted-foreground">
                {!isConfigLoading && !keyPredefined && (
                  <div className="grid gap-1">
                    <Label
                      htmlFor="openai-key"
                      className="text-xs text-foreground"
                    >
                      OpenAI API Key
                    </Label>
                    <Input
                      id="openai-key"
                      type="password"
                      placeholder="sk-&hellip;"
                      value={openaiKey}
                      onChange={handleKeyChange}
                    />
                  </div>
                )}
                <div className="grid gap-1">
                  <Label
                    htmlFor="model-select"
                    className="text-xs text-foreground"
                  >
                    Model
                  </Label>
                  <Select value={model} onValueChange={setModel}>
                    <SelectTrigger id="model-select" className="w-full">
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="codex-gpt-5.2">
                        codex-gpt-5.2
                      </SelectItem>
                      <SelectItem value="codex-gpt-5.1-codex-max">
                        codex-gpt-5.1-codex-max
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {!isAuthLoading && !isAuthorized && (
                  <span className="text-base font-serif text-muted-foreground">
                    <a
                      href={`${API_BASE}/v1/auth/`}
                      className="text-foreground underline underline-offset-2 hover:text-primary"
                    >
                      Authorize
                    </a>{" "}
                    to start analysis.
                  </span>
                )}
                <Button
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  className="w-full uppercase"
                >
                  {isSubmitting ? "Uploading…" : "Start analysis"}
                </Button>
                {submitError && (
                  <div className="text-xs text-destructive">{submitError}</div>
                )}

                {recentJobs.length > 0 && (
                  <div className="pt-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-xs text-muted-foreground">
                        Recent runs
                      </span>
                      <button
                        type="button"
                        onClick={() => setRecentJobs([])}
                        className="text-xs text-muted-foreground hover:text-foreground"
                      >
                        Clear
                      </button>
                    </div>
                    <div className="mt-2 space-y-1">
                      {recentJobs.slice(0, 6).map((job) => (
                        <button
                          key={job.job_id}
                          type="button"
                          onClick={() =>
                            router.push(`/results?job_id=${job.job_id}`)
                          }
                          className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted/40"
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
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
      <AppFooter showBorder={false} />
    </main>
  )
}
