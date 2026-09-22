// PLAN §10: running job with live log tail (poll every 2 s), failed jobs with retry.
import Stub from './Stub'

export default function Jobs() {
  // TODO(T4): useQuery with refetchInterval: 2000 while any job is 'running'.
  return (
    <Stub
      title="Jobs"
      plan="PLAN §9, §10 — queue, retries, logs"
      todo={[
        'Queue table: kind, episode, status, attempts, timings',
        'Live log tail for the running job (poll GET /jobs/{id}/log every 2 s)',
        'Retry button on failed jobs → POST /jobs/{id}/retry',
        'One worker processes one episode at a time — show the queue depth, not a fake ETA',
      ]}
    />
  )
}
