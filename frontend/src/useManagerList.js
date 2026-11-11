import { useEffect, useRef, useState } from 'react'
import { api } from './api'

// Poll only the requested page. Sequence + cleanup guards reject old replies
// after a filter/page change, retry, or navigation away from the screen.
export default function useManagerList(path) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const loadRef = useRef(null)
  useEffect(() => {
    let current = true
    let sequence = 0
    const load = async () => {
      const request = ++sequence
      setLoading(true)
      try {
        const reply = await api(path)
        if (current && request === sequence) { setData(reply); setError('') }
      } catch (err) { if (current && request === sequence) setError(err.message) }
      finally { if (current && request === sequence) setLoading(false) }
    }
    loadRef.current = load
    load()
    const timer = setInterval(load, 15000)
    return () => { current = false; clearInterval(timer); loadRef.current = null }
  }, [path])
  return { data, error, loading, refresh: () => loadRef.current?.() }
}
