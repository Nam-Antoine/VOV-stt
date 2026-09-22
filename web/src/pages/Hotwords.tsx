// PLAN §10: CRUD + "re-run affected episodes".
import Stub from './Stub'

export default function Hotwords() {
  return (
    <Stub
      title="Hotwords"
      plan="PLAN §9, §10 — contextual biasing terms"
      todo={[
        'Table: term, weight, note, active; inline add/edit/deactivate',
        'Store terms exactly as typed — casing and diacritics matter to the bpe match',
        '"Re-run affected episodes" → POST /hotwords/rerun-all',
        'Re-run only touches episodes with NO verified utterances (PLAN §0.2)',
        'Hotwords require modified_beam_search — surface that if decoding is greedy',
      ]}
    />
  )
}
