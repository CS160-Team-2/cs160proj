import React from 'react'

// A friendly error box: what went wrong, then buttons or links for what to do next.
const ProblemPanel = ({ title, message, children }) => (
  <div className="border-t-2 pt-14 pb-10 text-center text-gray-700" role="alert">
    <h1 className="text-2xl">{title}</h1>
    {message && <p className="mt-2 text-gray-600">{message}</p>}
    <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center items-center">{children}</div>
  </div>
)

export default ProblemPanel
