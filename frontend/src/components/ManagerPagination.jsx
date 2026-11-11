import React from 'react'

export default function ManagerPagination({ value, loading, onPage, onSize }) {
  if (!value) return null
  const { page, per_page: size, total, total_pages: pages } = value
  return <nav aria-label="Results pages" className="my-5 flex flex-wrap items-center gap-3 text-sm">
    <p role="status">{total ? `Showing ${(page - 1) * size + 1}–${Math.min(page * size, total)} of ${total}` : '0 results'} · Page {page} of {pages}</p>
    <button type="button" disabled={loading || page <= 1} onClick={() => onPage(page - 1)} className="border px-3 py-2 disabled:opacity-50">Previous page</button>
    <button type="button" disabled={loading || page >= pages} onClick={() => onPage(page + 1)} className="border px-3 py-2 disabled:opacity-50">Next page</button>
    <label className="flex items-center gap-2">Rows per page<select value={size} disabled={loading} onChange={(event) => onSize(Number(event.target.value))} className="border px-2 py-2">{[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
  </nav>
}
