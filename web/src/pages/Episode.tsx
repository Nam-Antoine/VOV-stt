// PLAN §10: "the Episode screen is the product".
//
// Layout: waveform + play controls pinned top; transcript below, grouped into
// utterances, each with a coloured speaker chip and a timestamp.
//
// Keyboard (PLAN §10):
//   Space   play/pause
//   [ / ]   previous / next utterance
//   L       loop current utterance
//   Ctrl+Z  revert utterance to text_asr
//
// Click a word → seek and play from that word. That single interaction is what makes
// verification 2x faster; everything else on this screen is secondary to it.
import Stub from './Stub'

export default function Episode() {
  // TODO(T4):
  //   const { id } = useParams()
  //   const episode = useQuery(['episode', id], () => api.getEpisode(id!))
  //   const transcript = useQuery(['transcript', tid], () => api.getTranscript(tid))
  //   <WaveformPlayer ref={player} src={api.audioUrl(tid)} />
  //   <SpeakerLegend ... />  <ConfidenceToggle ... />
  //   <TranscriptEditor onWordClick={(w) => player.seekAndPlay(w.start_s)} ... />
  return (
    <Stub
      title="Episode"
      plan="PLAN §10 — player + transcript editor (the core screen)"
      todo={[
        'WaveformPlayer (wavesurfer) pinned top, with loop-utterance',
        'Click a word → seek and play from that word (±200 ms target, PLAN §2.2)',
        'Inline-editable utterances; amber until saved; PATCH on blur, optimistic',
        'Ctrl+Z reverts to text_asr; Space / [ / ] / L shortcuts',
        'Show-confidence toggle: dotted underline below the 15th percentile',
        'Speaker legend: rename cluster → label, applies to the whole episode',
        'Flags per utterance: overlap / unclear / music / not-speech',
        'Progress "142 / 388 verified" + "mark episode verified"',
        'Read-only diff view: text_asr vs text_verified (feeds the hotword loop)',
        'spellcheck / autocapitalize / autocorrect OFF on every editable element',
      ]}
    />
  )
}
