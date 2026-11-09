import React, { useContext, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import ManagerLayout from '../components/ManagerLayout'

const blankStaff = { full_name: '', email: '', phone: '', role: 'employee', password: '' }

const StaffForm = ({ account, roleProtected, busy, error, onSubmit, onCancel }) => {
  const editing = Boolean(account)
  const [form, setForm] = useState(account ? {
    full_name: account.full_name, email: account.email,
    phone: account.phone || '', role: account.role, password: '',
  } : { ...blankStaff })
  const change = (name) => (event) => setForm((previous) => ({ ...previous, [name]: event.target.value }))

  const submit = (event) => {
    event.preventDefault()
    const values = {
      full_name: form.full_name.trim(), email: form.email.trim(),
      phone: form.phone.trim() || null, role: form.role,
    }
    if (!editing) values.password = form.password
    onSubmit(values)
  }

  return (
    <section aria-labelledby="staff-form-title" className="border border-gray-300 bg-gray-50 p-5 mb-6">
      <h2 id="staff-form-title" className="font-medium mb-4">{editing ? 'Edit staff account' : 'Add staff account'}</h2>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="grid sm:grid-cols-2 gap-4 disabled:opacity-70">
          <label className="flex flex-col gap-1 text-sm">Full name
            <input autoFocus name="full_name" value={form.full_name} onChange={change('full_name')} required maxLength={120} className="border border-gray-300 bg-white px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1 text-sm">Email
            <input name="email" type="email" value={form.email} onChange={change('email')} required maxLength={255} autoComplete="off" className="border border-gray-300 bg-white px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1 text-sm">Phone (optional)
            <input name="phone" type="tel" value={form.phone} onChange={change('phone')} maxLength={30} autoComplete="off" className="border border-gray-300 bg-white px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1 text-sm">Role
            <select name="role" value={form.role} onChange={change('role')} disabled={roleProtected} className="border border-gray-300 bg-white px-3 py-2 disabled:bg-gray-100">
              <option value="employee">Employee</option>
              <option value="manager">Manager</option>
            </select>
          </label>
          {roleProtected && <p className="text-xs text-gray-600 sm:col-span-2">Your own manager role and the last active manager role are protected.</p>}
          {!editing && <label className="flex flex-col gap-1 text-sm sm:col-span-2">Initial password
            <input name="password" type="password" value={form.password} onChange={change('password')} required minLength={8} autoComplete="new-password" className="border border-gray-300 bg-white px-3 py-2" />
            <span className="text-xs text-gray-600">At least 8 characters. The password is not shown in the staff list.</span>
          </label>}
          <div className="flex flex-wrap gap-3 sm:col-span-2">
            <button type="submit" className="bg-green-600 text-white px-5 py-2 text-sm">{busy ? 'Saving...' : editing ? 'Save staff changes' : 'Create staff account'}</button>
            <button type="button" onClick={onCancel} className="border border-gray-300 bg-white px-5 py-2 text-sm">Cancel</button>
          </div>
        </fieldset>
        {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      </form>
    </section>
  )
}

const ManagerStaff = () => {
  const { user, updateUser } = useContext(StoreContext)
  const manager = user?.role === 'manager'
  const [staff, setStaff] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const [form, setForm] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [formError, setFormError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!manager) return
    let current = true
    setLoading(true)
    setError('')
    api('/api/admin/staff').then((data) => {
      if (current) setStaff(data.staff)
    }).catch((err) => {
      if (current) setError(err.message)
    }).finally(() => {
      if (current) setLoading(false)
    })
    return () => { current = false }
  }, [manager, refresh])

  if (user === undefined) return <p role="status" className="pt-14 text-gray-600">Checking your account...</p>
  if (!user) return <Navigate to="/login?next=/manager/staff" replace />
  if (!manager) return <Navigate to={user.role === 'employee' ? '/inventory' : '/'} replace />

  const activeManagers = staff?.filter((account) => account.role === 'manager' && account.is_active).length || 0
  const isProtected = (account) => account.user_id === user.user_id ||
    (account.role === 'manager' && account.is_active && activeManagers <= 1)
  const merge = (account) => {
    setStaff((current) => {
      const rows = current || []
      return rows.some((row) => row.user_id === account.user_id)
        ? rows.map((row) => row.user_id === account.user_id ? account : row)
        : [...rows, account]
    })
    if (account.user_id === user.user_id) updateUser?.({ ...user, ...account })
  }
  const openForm = (account = null) => {
    setForm({ account })
    setConfirmation(null)
    setFormError('')
    setError('')
    setNotice('')
  }
  const save = async (values) => {
    const account = form.account
    setBusy('save')
    setFormError('')
    try {
      const data = await api(account ? `/api/admin/staff/${account.user_id}` : '/api/admin/staff', {
        method: account ? 'PATCH' : 'POST', body: values,
      })
      merge(data.staff)
      setForm(null) // Unmounting clears the password input and its component state.
      setNotice(`${account ? 'Updated' : 'Created'} ${data.staff.full_name}.`)
    } catch (err) { setFormError(err.message) }
    finally { setBusy('') }
  }
  const setActive = async (account, active) => {
    setBusy(String(account.user_id))
    setError('')
    setNotice('')
    try {
      const data = await api(`/api/admin/staff/${account.user_id}`, active
        ? { method: 'PATCH', body: { is_active: true } }
        : { method: 'DELETE' })
      merge(data.staff)
      setConfirmation(null)
      setNotice(`${active ? 'Reactivated' : 'Deactivated'} ${data.staff.full_name}.`)
    } catch (err) { setError(err.message) }
    finally { setBusy('') }
  }
  const rows = [...(staff || [])].sort((a, b) => a.full_name.localeCompare(b.full_name) || a.user_id - b.user_id)

  return (
    <ManagerLayout title="STAFF">
      <p className="text-sm text-gray-600 mb-5">Add employee or manager accounts, update their details, and manage access. Deactivation preserves their history. Your own account and the last active manager are protected.</p>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <button type="button" disabled={loading || Boolean(busy)} onClick={() => openForm()} className="bg-green-600 text-white px-5 py-2 text-sm disabled:opacity-50">Add staff account</button>
        <button type="button" disabled={loading || Boolean(busy)} onClick={() => setRefresh((value) => value + 1)} className="text-sm text-green-700 underline disabled:opacity-50">Refresh staff</button>
      </div>
      {notice && <p role="status" className="mb-4 bg-green-50 border border-green-600 p-3 text-sm text-green-800">{notice}</p>}
      {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}
      {form && <StaffForm key={form.account?.user_id || 'new'} account={form.account} roleProtected={form.account ? isProtected(form.account) : false} busy={Boolean(busy)} error={formError} onSubmit={save} onCancel={() => { setForm(null); setFormError('') }} />}
      {confirmation && <section role="dialog" aria-labelledby="deactivate-title" aria-describedby="deactivate-description" className="border border-amber-500 bg-amber-50 p-5 mb-6">
        <h2 id="deactivate-title" className="font-medium">Deactivate {confirmation.full_name}?</h2>
        <p id="deactivate-description" className="text-sm text-gray-700 mt-2">They will lose access immediately. Their account and work history will be retained, and a manager can reactivate them later.</p>
        <div className="mt-4 flex flex-wrap gap-3"><button type="button" disabled={Boolean(busy)} onClick={() => setActive(confirmation, false)} className="bg-red-700 text-white px-4 py-2 text-sm disabled:opacity-50">Confirm deactivation</button><button autoFocus type="button" disabled={Boolean(busy)} onClick={() => setConfirmation(null)} className="border border-gray-300 bg-white px-4 py-2 text-sm disabled:opacity-50">Cancel deactivation</button></div>
      </section>}
      {loading && <p role="status" className="mb-4 text-sm text-gray-600">Loading staff accounts...</p>}
      {staff && rows.length === 0 && <p className="text-gray-600">No staff accounts were found.</p>}
      {staff && rows.length > 0 && <div className="overflow-x-auto border border-gray-200">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Staff accounts and access</caption>
          <thead className="bg-gray-50 text-gray-700"><tr><th scope="col" className="p-3">Name</th><th scope="col" className="p-3">Contact</th><th scope="col" className="p-3">Role</th><th scope="col" className="p-3">Status</th><th scope="col" className="p-3">Actions</th></tr></thead>
          <tbody>{rows.map((account) => <tr key={account.user_id} className="border-t border-gray-200">
            <th scope="row" className="p-3 font-medium">{account.full_name}{account.user_id === user.user_id && <span className="block text-xs font-normal text-gray-500">Your account</span>}</th>
            <td className="p-3"><p className="break-all">{account.email}</p>{account.phone && <p className="text-gray-500">{account.phone}</p>}</td>
            <td className="p-3">{account.role === 'manager' ? 'Manager' : 'Employee'}</td>
            <td className="p-3"><span className={account.is_active ? 'text-green-700' : 'text-gray-500'}>{account.is_active ? 'Active' : 'Inactive'}</span></td>
            <td className="p-3"><div className="flex flex-wrap gap-3">
              <button type="button" disabled={Boolean(busy) || loading} onClick={() => openForm(account)} aria-label={`Edit ${account.full_name}`} className="text-green-700 underline disabled:opacity-50">Edit</button>
              {account.is_active
                ? <button type="button" disabled={Boolean(busy) || loading || isProtected(account)} onClick={() => { setConfirmation(account); setForm(null); setFormError(''); setError(''); setNotice('') }} aria-label={`Deactivate ${account.full_name}`} className="text-red-700 underline disabled:opacity-50">Deactivate</button>
                : <button type="button" disabled={Boolean(busy) || loading} onClick={() => setActive(account, true)} aria-label={`Reactivate ${account.full_name}`} className="text-green-700 underline disabled:opacity-50">Reactivate</button>}
            </div></td>
          </tr>)}</tbody>
        </table>
      </div>}
    </ManagerLayout>
  )
}

export default ManagerStaff
