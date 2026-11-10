import React, { useContext, useState } from 'react'
import { Link } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import ManagerAccess from '../components/ManagerAccess'
import ManagerLayout from '../components/ManagerLayout'
import ManagerPagination from '../components/ManagerPagination'
import useManagerList from '../useManagerList'

const labels = { declined: 'Declined payment', refunded: 'Recorded refund', payment_review: 'Payment needs review', unscheduled: 'Unscheduled order' }

function Problems() {
  const { currency } = useContext(StoreContext)
  const [draft, setDraft] = useState({ kind: '', from: '', to: '' })
  const [filters, setFilters] = useState(draft)
  const [filterError, setFilterError] = useState('')
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(25)
  const params = new URLSearchParams({ page, per_page: size })
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value)
  const { data, error, loading, refresh } = useManagerList(`/api/admin/problems?${params}`)
  const apply = (values) => {
    if (values.from && values.to && values.from > values.to) { setFilterError('From date must be on or before To date.'); return }
    setFilterError(''); setPage(1); setFilters({ ...values })
  }
  return <ManagerLayout title="PROBLEMS">
    <p className="text-sm text-gray-600 mb-4">Review recorded payment failures/refunds, payments needing review, and current delivery scheduling problems, newest first. Failed checkouts may have no order number.</p>
    <p className="text-sm text-gray-600 mb-5">Scheduling dates show when the order was placed. Scheduling problems disappear when resolved; payment attempts remain recorded.</p>
    <form onSubmit={(event) => { event.preventDefault(); apply(draft) }} className="flex flex-wrap gap-3 items-end mb-5">
      <label className="flex flex-col gap-1 text-sm">Problem type<select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })} className="border px-3 py-2"><option value="">All problems</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {['from', 'to'].map((key) => <label key={key} className="flex flex-col gap-1 text-sm">{key === 'from' ? 'From date' : 'To date'}<input type="date" value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} className="border px-3 py-2" /></label>)}
      <button className="bg-green-600 text-white px-4 py-2 text-sm">Apply filters</button>
      <button type="button" onClick={() => { const blank = { kind: '', from: '', to: '' }; setDraft(blank); apply(blank) }} className="underline text-green-700 text-sm py-2">Clear filters</button>
      <button type="button" onClick={refresh} className="underline text-green-700 text-sm py-2">Refresh problems</button>
    </form>
    {filterError && <p role="alert" className="text-red-700 mb-3">{filterError}</p>}
    {error && <p role="alert" className="text-red-700 mb-3">Could not refresh problems: {error}{data && ' Showing the last successful results.'} <button onClick={refresh} className="underline">Retry problems</button></p>}
    {loading && <p role="status">{data ? 'Refreshing problems...' : 'Loading problems...'}</p>}
    {data?.problems.length === 0 && <p className="text-gray-600">No problems match these filters.</p>}
    <div className="flex flex-col gap-4 mt-4" aria-busy={loading}>
      {data?.problems.map((problem) => <article key={problem.problem_id} className="border border-gray-300 p-4 text-sm min-w-0">
        <h2 className="font-medium">{labels[problem.kind]}</h2>
        <p className="text-gray-500">{problem.time_label}: {new Date(problem.occurred_at).toLocaleString()}</p>
        <p className="my-2 break-words whitespace-pre-wrap">{problem.reason}</p>
        {problem.order_number ? <Link className="text-green-700 underline break-all" to={`/manager?q=${encodeURIComponent(problem.order_number)}`}>View order {problem.order_number}</Link> : <p>No order created for this payment attempt.</p>}
        {problem.kind === 'payment_review' && <p className="mt-2 font-medium text-red-700">Check the payment gateway before taking any financial action. This screen does not issue refunds.</p>}
        {problem.transaction_id != null && <div className="mt-2 text-gray-600 break-all"><p>Transaction #{problem.transaction_id} · {currency}{problem.amount}</p><p>Gateway reference: {problem.gateway_ref || 'Not recorded'} · Card ending: {problem.card_last4 || 'Not recorded'}</p></div>}
        {problem.kind === 'unscheduled' && <p className="mt-2"><Link to="/manager/delivery" className="text-green-700 underline">Open delivery board</Link></p>}
      </article>)}
    </div>
    <ManagerPagination value={data?.pagination} loading={loading} onPage={setPage} onSize={(value) => { setSize(value); setPage(1) }} />
  </ManagerLayout>
}

export default function ManagerProblems() { return <ManagerAccess><Problems /></ManagerAccess> }
