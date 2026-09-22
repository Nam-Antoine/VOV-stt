// PLAN §10: status chips, bulk "enqueue all ingested", upload dropzone, URL box.
import Stub from './Stub'

export default function Episodes() {
  // TODO(T4): useQuery(['episodes', filter], () => api.listEpisodes(filter))
  return (
    <Stub
      title="Episodes"
      plan="PLAN §10 — list, status chips, upload/URL ingest, bulk enqueue"
      todo={[
        'Table: slug, title, air date, duration, status chip, utterances verified / total',
        'Filter by status; search over title and slug',
        'Upload dropzone → POST /episodes/upload (multipart)',
        'URL box → POST /episodes/from-url (manual ingest only, no crawler — PLAN §9)',
        'Bulk "enqueue all ingested" → POST /episodes/{id}/transcribe per row',
        'Row click → /episodes/:id',
      ]}
    />
  )
}
