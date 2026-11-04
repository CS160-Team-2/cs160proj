import React from 'react'

const ArrivalEstimate = ({ value }) => {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const late = date.getTime() < Date.now()
  return <div className="text-sm text-gray-700"><p>{late ? 'Original arrival estimate' : 'Estimated arrival'}: <b>{date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</b></p>{late && <p className="text-amber-800">Delivery is taking longer than estimated. Waiting for an updated arrival time.</p>}</div>
}

export default ArrivalEstimate
