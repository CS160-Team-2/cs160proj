import React, { useState } from 'react'
import { api } from '../api'

const formatTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')

const lineLabel = (numbers) => `${numbers.length > 1 ? 'lines' : 'line'} ${numbers.join(', ')}`

const asForm = (file) => {
  const form = new FormData()
  form.append('file', file)
  return form
}

// Managers restock from a delivery manifest (a CSV of product_name,quantity).
// Choosing a file shows what would change; nothing is saved until APPLY,
// and the backend refuses the whole file if any line has a problem.
// onApplied runs after a manifest is saved, so the page can reload stock.
const ManifestUpload = ({ onApplied }) => {

  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  // Changing the key empties the file input, so the same file can be chosen again.
  const [inputKey, setInputKey] = useState(0)

  const reset = () => {
    setFile(null)
    setPreview(null)
    setError('')
    setInputKey(inputKey + 1)
  }

  const choose = async (e) => {
    const chosen = e.target.files[0]
    if (!chosen) return
    setFile(chosen)
    setPreview(null)
    setError('')
    setNotice('')
    try {
      setPreview(await api('/api/admin/inventory/manifest/preview', { method: 'POST', body: asForm(chosen) }))
    } catch (err) {
      setError(err.message)
    }
  }

  const apply = async () => {
    setBusy(true)
    setError('')
    try {
      const { manifest } = await api('/api/admin/inventory/manifest', { method: 'POST', body: asForm(file) })
      reset()
      setNotice(`Added ${manifest.total_units} units from ${manifest.filename} (manifest #${manifest.manifest_id}).`)
      onApplied()
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  return (
    <div className="mb-6 border p-4 text-gray-700">
      <p className="font-medium">Delivery manifest</p>
      <p className="text-sm text-gray-500 mb-3">
        Upload a CSV file with the columns product_name and quantity. You will see the changes before anything is saved.
      </p>
      <input
        key={inputKey}
        type="file"
        accept=".csv,text/csv"
        aria-label="Delivery manifest file"
        onChange={choose}
        className="text-sm"
      />

      {preview && (
        <div className="mt-4">
          {preview.already_applied && (
            <p className="mb-3 text-sm text-red-600">
              This file was already applied as manifest #{preview.already_applied.manifest_id} by{' '}
              {preview.already_applied.applied_by} on {formatTime(preview.already_applied.applied_at)}.
            </p>
          )}

          {preview.problems.length > 0 && (
            <div className="mb-3 text-sm text-red-600">
              <p className="font-medium">Nothing can be applied until these are fixed in the file:</p>
              {preview.problems.map((problem, i) => (
                <p key={i}>{problem.line ? `Line ${problem.line}: ` : ''}{problem.message}</p>
              ))}
            </div>
          )}

          {preview.lines.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-gray-500">
                  <tr>
                    <th className="py-1 pr-3 font-normal">Product</th>
                    <th className="py-1 pr-3 font-normal">From</th>
                    <th className="py-1 pr-3 font-normal text-right">Now</th>
                    <th className="py-1 pr-3 font-normal text-right">Adding</th>
                    <th className="py-1 font-normal text-right">After</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.lines.map((line) => (
                    <tr key={line.product_id} className="border-t">
                      <td className="py-1 pr-3">
                        {line.name}
                        {!line.is_listed && <span className="ml-2 text-gray-500">UNLISTED</span>}
                      </td>
                      <td className="py-1 pr-3 text-gray-500">{lineLabel(line.line_numbers)}</td>
                      <td className="py-1 pr-3 text-right">{line.stock_now}</td>
                      <td className="py-1 pr-3 text-right text-green-700">+{line.quantity}</td>
                      <td className="py-1 text-right font-medium">{line.stock_after}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex gap-2 mt-3">
            {preview.can_apply && (
              <button onClick={apply} disabled={busy} className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400">
                APPLY MANIFEST
              </button>
            )}
            <button onClick={reset} aria-label="CANCEL MANIFEST" className="border text-sm px-6 py-2">CANCEL</button>
          </div>
        </div>
      )}

      {notice && <p className="mt-3 text-sm text-green-600">{notice}</p>}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  )
}

export default ManifestUpload
