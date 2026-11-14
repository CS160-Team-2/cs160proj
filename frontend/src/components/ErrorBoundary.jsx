import React from 'react'
import { Link } from 'react-router-dom'
import ProblemPanel from './ProblemPanel'

// Catches a crash while drawing a page so the customer sees a way out instead of a blank screen.
class ErrorBoundary extends React.Component {

  state = { failed: false }

  // Marks the boundary as failed when a child throws while rendering.
  static getDerivedStateFromError() {
    return { failed: true }
  }

  // Writes the crash to the console for developers.
  componentDidCatch(error) {
    console.error('Page crashed:', error)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <ProblemPanel title="Something went wrong" message="This page hit a problem. Your cart and order are safe. Try reloading, or go back to the shop.">
        <button type="button" onClick={() => window.location.reload()} className="bg-green-600 text-white px-8 py-3 text-sm">RELOAD PAGE</button>
        <Link to="/" onClick={() => this.setState({ failed: false })} className="border border-gray-800 px-8 py-3 text-sm">GO TO HOME</Link>
      </ProblemPanel>
    )
  }
}

export default ErrorBoundary
