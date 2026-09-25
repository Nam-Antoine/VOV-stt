// Vietnamese display labels for API enum values. The API keeps its English values;
// only what the operator reads is translated.
import type { EpisodeStatus, JobKind, JobStatus } from './api/types'

export const EPISODE_STATUS_LABEL: Record<EpisodeStatus, string> = {
  ingested: 'Đã tải lên',
  queued: 'Đang chờ',
  processing: 'Đang xử lý',
  transcribed: 'Đã chép lời',
  verifying: 'Đang duyệt',
  verified: 'Đã duyệt',
  failed: 'Lỗi',
}

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  queued: 'Đang chờ',
  running: 'Đang chạy',
  done: 'Hoàn tất',
  failed: 'Lỗi',
}

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  transcribe: 'Chép lời',
  export: 'Xuất file',
  google_sync: 'Đồng bộ Google',
}
