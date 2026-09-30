// Projects: one Drive folder + index Sheet per programme. "Đàn bà 30+" is the first
// one; new programmes (other VOV shows, etc.) get their own from here.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import { Check, Copy, Folder, Pencil, Plus, Sheet, Spinner, Trash } from '../components/Icons'
import { rememberProject } from '../lastProject'
import type { Project } from '../api/types'

function NewProjectForm({ onCreated }: { onCreated: (p: Project) => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const queryClient = useQueryClient()

  const create = useMutation({
    mutationFn: () => api.createProject({ name: name.trim(), description: description.trim() || undefined }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setOpen(false)
      setName('')
      setDescription('')
      onCreated(project)
    },
  })

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-primary">
        <Plus className="h-4 w-4" />
        Dự án mới
      </button>
    )
  }

  return (
    <form
      className="card w-full max-w-md space-y-3 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim()) create.mutate()
      }}
    >
      <div>
        <label className="text-xs font-medium text-muted">Tên chương trình</label>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
          placeholder="vd. Quà tặng cuộc sống"
          className="field mt-1 w-full"
        />
      </div>
      <div>
        <label className="text-xs font-medium text-muted">Mô tả (tuỳ chọn)</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={2000}
          className="field mt-1 w-full"
        />
      </div>
      {create.isError && (
        <p className="text-xs text-rose-600">
          {create.error instanceof ApiError ? create.error.detail : 'Không tạo được dự án'}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary btn-sm" disabled={!name.trim() || create.isPending}>
          {create.isPending ? <Spinner className="h-3.5 w-3.5" /> : 'Tạo'}
        </button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => setOpen(false)}>
          Huỷ
        </button>
      </div>
    </form>
  )
}

// "<project name>:<Sheet link>", the line the owner pastes to the client.
const sheetLine = (p: Project) => `${p.name}:${p.sheet_url}`

function CopyButton({ text, label, caption, className = 'btn-ghost btn-sm' }: {
  text: string
  label: string
  /** Visible text next to the icon; icon-only when omitted. */
  caption?: string
  className?: string
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      // No clipboard access (plain-http origin, permission denied).
      setState('failed')
    }
    setTimeout(() => setState('idle'), 2000)
  }

  const title = { idle: label, copied: 'Đã sao chép', failed: 'Không sao chép được' }[state]
  return (
    <button onClick={copy} className={className} title={title} aria-label={title}>
      {state === 'copied' ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy />}
      {state === 'failed' ? <span className="text-xs text-rose-600">{title}</span>
        : caption && <span>{state === 'copied' ? title : caption}</span>}
    </button>
  )
}

function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<'name' | 'description' | null>(null)
  const [draft, setDraft] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const patch = useMutation({
    mutationFn: (payload: Partial<{ name: string; description: string }>) =>
      api.patchProject(project.id, payload),
    onSuccess: () => {
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteProject(project.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
  })

  const open = () => {
    rememberProject(project.id)
    navigate(`/projects/${project.id}`)
  }

  return (
    <div className="card flex flex-col gap-3 p-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-ink">
          <Folder className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          {editing === 'name' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (draft.trim()) patch.mutate({ name: draft.trim() })
              }}
              className="flex items-center gap-1.5"
            >
              <input
                autoFocus
                value={draft}
                maxLength={200}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && setEditing(null)}
                className="field flex-1 text-sm"
              />
              <button type="submit" className="btn-primary btn-sm">Lưu</button>
              <button type="button" className="btn-ghost btn-sm" onClick={() => setEditing(null)}>Huỷ</button>
            </form>
          ) : (
            <button
              onClick={open}
              className="text-left font-reading text-lg font-medium hover:text-accent-strong"
            >
              {project.name}
            </button>
          )}
          <p className="mt-0.5 text-xs text-faint">
            {project.n_episodes} tập · {project.n_transcribed} đã chép lời · {project.n_verified} đoạn đã duyệt
            {project.hours_verified > 0 && ` · ${project.hours_verified.toLocaleString('vi-VN')} giờ`}
          </p>
        </div>
      </div>

      {editing === 'description' ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            patch.mutate({ description: draft })
          }}
          className="flex items-center gap-1.5"
        >
          <input
            autoFocus
            value={draft}
            maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setEditing(null)}
            className="field flex-1 text-sm"
          />
          <button type="submit" className="btn-primary btn-sm">Lưu</button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => setEditing(null)}>Huỷ</button>
        </form>
      ) : (
        <button
          onClick={() => {
            setDraft(project.description ?? '')
            setEditing('description')
          }}
          className="text-left text-sm text-muted hover:text-ink"
        >
          {project.description || 'Thêm mô tả…'}
        </button>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <button onClick={open} className="btn-outline btn-sm">Mở</button>
        {project.sheet_url && (
          <a
            href={project.sheet_url}
            target="_blank"
            rel="noreferrer"
            className="btn-ghost btn-sm"
            title="Mở Google Sheet"
            aria-label="Mở Google Sheet"
          >
            <Sheet />
          </a>
        )}
        {project.sheet_url && (
          <CopyButton text={sheetLine(project)} label="Sao chép tên dự án và link Sheet" />
        )}
        <button
          onClick={() => {
            setDraft(project.name)
            setEditing('name')
          }}
          className="btn-ghost btn-sm"
          title="Đổi tên dự án"
          aria-label="Đổi tên dự án"
        >
          <Pencil />
        </button>
        {project.n_episodes === 0 && (
          <span className="ml-auto">
            {confirmDelete ? (
              <span className="flex items-center gap-2 text-xs">
                <span className="text-muted">Xoá dự án trống này?</span>
                <button
                  onClick={() => remove.mutate()}
                  className="text-rose-600 hover:underline"
                  disabled={remove.isPending}
                >
                  Xoá
                </button>
                <button onClick={() => setConfirmDelete(false)} className="text-muted hover:underline">
                  Huỷ
                </button>
              </span>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="btn-ghost btn-sm text-muted hover:text-rose-600"
                title="Xoá dự án trống"
                aria-label="Xoá dự án"
              >
                <Trash className="h-4 w-4" />
              </button>
            )}
          </span>
        )}
      </div>
    </div>
  )
}

export default function Projects() {
  const navigate = useNavigate()
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api.listProjects() })
  const rows = projects.data ?? []
  const summary = rows.filter((p) => p.sheet_url).map(sheetLine).join('\n')

  return (
    <section>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Kho ngữ liệu VN-STT</p>
          <h1 className="title mt-1">Các dự án</h1>
          <p className="mt-1.5 text-sm text-muted">
            Mỗi chương trình là một dự án riêng, với thư mục Google Drive và Sheet riêng.
          </p>
        </div>
        <div className="flex flex-wrap items-start gap-2">
          {summary && (
            <CopyButton
              text={summary}
              label="Sao chép tên và link Sheet của mọi dự án, mỗi dự án một dòng"
              caption="Sao chép tất cả"
              className="btn-outline"
            />
          )}
          <NewProjectForm
            onCreated={(p) => {
              rememberProject(p.id)
              navigate(`/projects/${p.id}`)
            }}
          />
        </div>
      </header>

      {projects.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-40 rounded-xl" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted">
          Chưa có dự án nào. Tạo một dự án để bắt đầu tải lên âm thanh.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </section>
  )
}
