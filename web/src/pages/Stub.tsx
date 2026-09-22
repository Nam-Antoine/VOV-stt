/** Shared placeholder while the T3 API handlers are stubs. */
export default function Stub({ title, plan, todo }: {
  title: string
  plan: string
  todo: string[]
}) {
  return (
    <section>
      <header className="mb-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-slate-500">{plan}</p>
      </header>
      <div className="rounded border border-amber-200 bg-amber-50 p-4 text-sm">
        <p className="font-medium text-amber-900">
          Skeleton only — the API endpoints behind this page return 501 until T3.
        </p>
        <ul className="mt-2 list-disc pl-5 text-amber-800">
          {todo.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}
