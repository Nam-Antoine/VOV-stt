// PLAN §10: CRUD + "re-run affected episodes".
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'
import { useIsAdmin } from '../api/session'
import HotwordSuggestions from '../components/HotwordSuggestions'

export default function Hotwords() {
  const queryClient = useQueryClient()
  const isAdmin = useIsAdmin()
  const [term, setTerm] = useState('')
  const [weight, setWeight] = useState(1.0)
  const [note, setNote] = useState('')

  const hotwords = useQuery({ queryKey: ['hotwords'], queryFn: () => api.listHotwords() })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['hotwords'] })

  const create = useMutation({
    mutationFn: () => api.createHotword({ term, weight, note: note || undefined }),
    onSuccess: () => {
      setTerm('')
      setNote('')
      invalidate()
    },
  })
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.patchHotword(id, { active }),
    onSuccess: invalidate,
  })
  const rerun = useMutation({ mutationFn: () => api.rerunAll() })

  const rows = hotwords.data ?? []

  return (
    <section>
      <header className="mb-6 flex flex-wrap items-end gap-3">
        <div className="min-w-0">
          <p className="eyebrow">Ưu tiên theo ngữ cảnh</p>
          <h1 className="title mt-1">Từ khóa</h1>
          <p className="mt-1.5 max-w-xl text-sm text-muted">
            Viết mỗi từ khóa bằng <b className="font-semibold text-ink">CHỮ IN HOA, đúng như khi đọc</b>,
            có đủ dấu — mô hình không có chữ thường, nên{' '}
            <span className="font-reading">ĐÀN BÀ BA MƯƠI CỘNG</span> là hợp lệ còn{' '}
            <span className="font-reading">Đàn bà 30+</span> sẽ bị từ chối.
          </p>
        </div>
        {isAdmin && (<button
          onClick={() => rerun.mutate()}
          className="btn-outline sm:ml-auto"
          title="Chỉ áp dụng cho các tập chưa có lượt lời nào được duyệt"
        >
          {rerun.isPending ? 'Đang đưa vào hàng chờ…' : 'Chạy lại các tập bị ảnh hưởng'}
        </button>)}
      </header>

      {rerun.isSuccess && (
        <p className="mb-3 rounded-lg border border-verified/30 bg-verified/10 p-3 text-sm text-ink">
          Đã đưa {rerun.data.length} tập vào hàng chờ. Các tập đã có lượt lời được duyệt
          được bỏ qua — chạy lại không bao giờ xóa công sức của người duyệt.
        </p>
      )}

      {!isAdmin && (
        <p className="mb-4 rounded-lg border border-line bg-surface p-3 text-sm text-muted">
          Chỉ quản trị viên được thêm, bật/tắt từ khóa và chạy lại các tập.
        </p>
      )}

      {isAdmin && (<form
        className="mb-4 flex flex-wrap items-end gap-2 rounded-lg border border-line bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <label className="text-sm">
          <span className="block text-xs text-muted">Từ khóa</span>
          <input
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            placeholder="THANH HUYỀN"
            className="w-56 rounded-xl border border-line px-2 py-1"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Trọng số</span>
          <input
            type="number"
            step="0.1"
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
            className="w-24 rounded-xl border border-line px-2 py-1"
          />
        </label>
        <label className="flex-1 text-sm">
          <span className="block text-xs text-muted">Ghi chú</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded-xl border border-line px-2 py-1"
          />
        </label>
        <button
          type="submit"
          disabled={!term || create.isPending}
          className="btn-primary disabled:opacity-40"
        >
          Thêm
        </button>
        {create.isError && (
          <p className="w-full text-sm text-rose-600">
            {create.error instanceof ApiError ? create.error.detail : 'Thất bại'}
          </p>
        )}
      </form>)}

      <HotwordSuggestions canAdd={isAdmin} />

      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-sunken text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Từ khóa</th>
              <th className="px-3 py-2">Trọng số</th>
              <th className="px-3 py-2">Ghi chú</th>
              <th className="px-3 py-2">Bật</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.id} className="border-t border-line">
                <td className="px-3 py-2 font-medium">{h.term}</td>
                <td className="px-3 py-2 tabular-nums">{h.weight}</td>
                <td className="px-3 py-2 text-muted">{h.note}</td>
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={h.active}
                    disabled={!isAdmin}
                    onChange={(e) => toggle.mutate({ id: h.id, active: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-faint">
        Từ khóa chỉ có tác dụng với cách giải mã modified_beam_search; chế độ greedy sẽ âm thầm
        bỏ qua chúng (CLAUDE.md quy tắc 5). Hệ thống lưu mã sha256 của danh sách từ khóa
        đã dùng cho mỗi bản chép lời.
      </p>
    </section>
  )
}
