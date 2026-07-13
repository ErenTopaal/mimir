"use client"

import { Folder01Icon } from "@hugeicons/core-free-icons"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { FileTreeNode } from "./file-tree-node"
import type { FileTreeProps } from "./types"

export function FileTree({
  nodes,
  selectedFile,
  onFileSelect,
  focusedPath,
  onFocusChange,
  expandedPaths,
  onToggleExpand,
  severityByPath,
}: FileTreeProps) {
  if (nodes.length === 0) {
    return (
      <Empty className="border-none px-2 py-8">
        <EmptyHeader>
          <HugeiconsIcon
            icon={Folder01Icon}
            strokeWidth={1.5}
            className="size-8 text-muted-foreground/60 mx-auto mb-2"
          />
          <EmptyTitle>No files loaded</EmptyTitle>
        </EmptyHeader>
        <EmptyContent>
          <EmptyDescription>
            Upload files to see them here
          </EmptyDescription>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <div className="text-sm">
      {nodes.map((node) => (
        <FileTreeNode
          key={node.path}
          node={node}
          selectedFile={selectedFile}
          onFileSelect={onFileSelect}
          focusedPath={focusedPath}
          onFocusChange={onFocusChange}
          expandedPaths={expandedPaths}
          onToggleExpand={onToggleExpand}
          severityByPath={severityByPath}
        />
      ))}
    </div>
  )
}
