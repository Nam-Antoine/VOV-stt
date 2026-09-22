// PLAN §9: per-episode exports and the corpus zip.
import Stub from './Stub'

export default function Exports() {
  return (
    <Stub
      title="Exports"
      plan="PLAN §1.5, §9 — json, verified.json, eaf, txt, csv, srt, corpus.zip"
      todo={[
        'Per-episode download links for each of the six formats',
        'Corpus zip with a tier selector (verified | all)',
        'Every export is regenerated from the raw JSON — nothing cached (PLAN §0.2)',
        'Renderers already exist in backend/app/exports and are covered by tests',
      ]}
    />
  )
}
