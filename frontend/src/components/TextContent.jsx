import React from 'react'

const TextContent = ({text1, text2}) => {
  return (
    <div className="inline-flex gap-2 items-center mb-3">
        <p className="w-10 sm:w-12 h-[1px] sm:h-[2px] bg-green-600"></p>
        <p className="text-green-600 font-bold">{text1} <span className="text-black font-medium">{text2}</span></p>
        <p className="w-10 sm:w-12 h-[1px] sm:h-[2px] bg-green-600"></p>
    </div>
  )
}

export default TextContent
