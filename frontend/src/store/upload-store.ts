import { create } from "zustand"
import { persist } from "zustand/middleware"

interface UploadState {
  files: File[] | null
  packageName: string | null
  setUpload: (files: File[] | null, packageName: string | null) => void
  clearUpload: () => void
}

export const useUploadStore = create<UploadState>()(
  persist(
    (set) => ({
      files: null,
      packageName: null,
      setUpload: (files, packageName) => set({ files, packageName }),
      clearUpload: () => set({ files: null, packageName: null }),
    }),
    {
      name: "avaxbench.upload",
      partialize: (state) => ({ packageName: state.packageName }),
    },
  ),
)
