"use client"

import { useRouter } from "next/navigation"
import { useCallback, useEffect, useMemo, useState } from "react"
import { AppFooter } from "@/components/app-footer"
import { AppHeader } from "@/components/app-header"
import { FileUploader } from "@/components/file-uploader"
import { RecentRuns } from "@/components/recent-runs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
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
import { detectInputType } from "@/lib/input-detection"
import { auditGithubRepo, fetchPermalink, startJob } from "@/lib/jobs"
import { addRecentJob, type RecentJob } from "@/lib/recent-jobs"
import { inferPackageName } from "@/lib/upload-utils"
import { createZipFromFiles } from "@/lib/zip"
import { useUploadStore } from "@/store/upload-store"

export default function Page() {
  const router = useRouter()
  const { files, packageName, setUpload, clearUpload } = useUploadStore()
  const [openaiKey, setOpenaiKey] = useState("")
  const [storedModel, setStoredModel] = useLocalStorage("avaxbench.model", "")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [oneBoxValue, setOneBoxValue] = useSessionStorage(
    "avaxbench.oneBox",
    "",
  )
  const oneBoxType = detectInputType(oneBoxValue)
  const [isOneBoxSubmitting, setIsOneBoxSubmitting] = useState(false)
  const [oneBoxError, setOneBoxError] = useState<string | null>(null)
  const [recentJobs, setRecentJobs] = useLocalStorage<RecentJob[]>(
    "avaxbench.recentJobs.v1",
    [],
  )
  const {
    isAuthorized,
    isLoading: isAuthLoading,
    isConfigLoading,
    keyPredefined,
    models,
  } = useAuth()

  // Sync model with backend-provided list
  const model =
    storedModel && models.includes(storedModel)
      ? storedModel
      : models[0] ?? ""

  useEffect(() => {
    if (models.length > 0 && (!storedModel || !models.includes(storedModel))) {
      setStoredModel(models[0])
    }
  }, [models, storedModel, setStoredModel])

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
      <AppHeader showLogo showBorder={false} />
      <section className="flex flex-1 flex-col items-center justify-center px-6 py-16">
        <div className="w-full max-w-lg space-y-8">
          {/* Hero */}
          <div className="animate-fade-in-up space-y-2 text-center">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              AvaxBench
            </h1>
            <p className="text-sm text-muted-foreground">
              AI-powered security analysis for Avalanche smart contracts.
            </p>
          </div>

          {/* Form */}
          <div
            className="animate-fade-in-up space-y-4"
            style={{ animationDelay: "80ms" }}
          >
            {/* One-box input */}
            <div className="grid gap-1.5">
              <Input
                id="one-box"
                type="text"
                placeholder="Paste 0x address, GitHub URL, or drop files below"
                value={oneBoxValue}
                onChange={(e) => {
                  setOneBoxValue(e.target.value)
                  setOneBoxError(null)
                }}
                disabled={isSubmitting || isOneBoxSubmitting}
              />
              {oneBoxType === "address" && (
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full"
                  disabled={isOneBoxSubmitting}
                  onClick={async () => {
                    const address = oneBoxValue.trim()
                    setIsOneBoxSubmitting(true)
                    setOneBoxError(null)
                    try {
                      const res = await fetchPermalink("avalanche", address, model)
                      if (res.job_id) {
                        router.push(`/results?job_id=${res.job_id}`)
                      } else if (res.status === "source_not_available") {
                        setOneBoxError(
                          "Source code not available for this address",
                        )
                      }
                    } catch (err) {
                      setOneBoxError(
                        err instanceof Error
                          ? err.message
                          : "Failed to trigger on-chain audit",
                      )
                    } finally {
                      setIsOneBoxSubmitting(false)
                    }
                  }}
                >
                  {isOneBoxSubmitting ? (
                    <span className="flex items-center gap-2">
                      <Spinner size="sm" />
                      Checking source…
                    </span>
                  ) : (
                    <>Audit on-chain &rarr;</>
                  )}
                </Button>
              )}
              {oneBoxType === "github" && (
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full"
                  disabled={isOneBoxSubmitting}
                  onClick={async () => {
                    const trimmed = oneBoxValue.trim().replace(/\/$/, "")
                    setIsOneBoxSubmitting(true)
                    setOneBoxError(null)
                    try {
                      const res = await auditGithubRepo(trimmed, model)
                      router.push(`/results?job_id=${res.job_id}`)
                    } catch (err) {
                      setOneBoxError(
                        err instanceof Error
                          ? err.message
                          : "Failed to trigger GitHub audit",
                      )
                    } finally {
                      setIsOneBoxSubmitting(false)
                    }
                  }}
                >
                  {isOneBoxSubmitting ? (
                    <span className="flex items-center gap-2">
                      <Spinner size="sm" />
                      Fetching repo…
                    </span>
                  ) : (
                    <>Audit from GitHub &rarr;</>
                  )}
                </Button>
              )}
              {oneBoxError && (
                <p className="text-xs text-destructive">{oneBoxError}</p>
              )}
            </div>

            {/* File uploader */}
            <FileUploader
              onFilesSelected={handleFilesSelected}
              files={files}
              selectedLabel={selectedLabel}
              fileCount={fileCount}
              disabled={isSubmitting}
              onClear={clearUpload}
            />

            {/* Model + key row */}
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
                <Select value={model} onValueChange={setStoredModel}>
                  <SelectTrigger id="model-select" className="w-full">
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Auth notice */}
              {!isAuthLoading && !isAuthorized && (
                <span className="text-sm text-muted-foreground">
                  <a
                    href={`${API_BASE}/v1/auth/`}
                    className="text-foreground underline underline-offset-2 hover:text-primary"
                  >
                    Authorize
                  </a>{" "}
                  to start analysis.
                </span>
              )}

              {/* Submit */}
              <Button
                onClick={handleSubmit}
                disabled={!canSubmit}
                className="h-11 w-full text-sm font-medium uppercase tracking-wider"
              >
                {isSubmitting ? (
                  <span className="flex items-center gap-2">
                    <Spinner size="md" />
                    Uploading…
                  </span>
                ) : (
                  "Start analysis"
                )}
              </Button>

              {submitError && (
                <div className="text-xs text-destructive">{submitError}</div>
              )}
            </div>
          </div>

          {/* Recent runs */}
          <div
            className="animate-fade-in-up"
            style={{ animationDelay: "160ms" }}
          >
            <RecentRuns
              jobs={recentJobs}
              onClear={() => setRecentJobs([])}
            />
          </div>
        </div>
      </section>
      <AppFooter showBorder={false} />
    </main>
  )
}
