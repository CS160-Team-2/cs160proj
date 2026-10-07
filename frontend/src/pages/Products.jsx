import React, { useContext, useMemo, useState } from 'react'
import { StoreContext } from '../context/StoreContext'
import TextContent from '../components/TextContent'
import StoreItem from '../components/StoreItem'

const priceRanges = [
  { label: 'Under $3', min: 0, max: 3 },
  { label: '$3 - $5', min: 3, max: 5 },
  { label: '$5 - $7', min: 5, max: 7 },
  { label: '$7 & above', min: 7, max: Infinity },
]

const shuffle = (list) => {
  const result = [...list]
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[result[i], result[j]] = [result[j], result[i]]
  }
  return result
}

const Products = () => {

  const { products } = useContext(StoreContext)

  const [showFilter, setShowFilter] = useState(false)
  const [categories, setCategories] = useState([])
  const [ranges, setRanges] = useState([])
  const [appliedCategories, setAppliedCategories] = useState([])
  const [appliedRanges, setAppliedRanges] = useState([])
  const [sortType, setSortType] = useState('random')

  const shuffled = useMemo(() => shuffle(products), [products])

  const categoryList = [...new Set(products.map((item) => item.category))].sort()

  const toggle = (value, list, setList) => {
    setList(list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value])
  }

  const applyFilters = () => {
    setAppliedCategories(categories)
    setAppliedRanges(ranges)
    setShowFilter(false)
  }

  const clearFilters = () => {
    setCategories([])
    setRanges([])
    setAppliedCategories([])
    setAppliedRanges([])
  }

  let visible = shuffled.filter((item) => {
    if (appliedCategories.length > 0 && !appliedCategories.includes(item.category)) return false
    if (appliedRanges.length > 0) {
      const price = Number(item.price)
      const inRange = appliedRanges.some((label) => {
        const range = priceRanges.find((entry) => entry.label === label)
        return price >= range.min && price < range.max
      })
      if (!inRange) return false
    }
    return true
  })

  if (sortType === 'name-asc') {
    visible = [...visible].sort((a, b) => a.name.localeCompare(b.name))
  } else if (sortType === 'name-desc') {
    visible = [...visible].sort((a, b) => b.name.localeCompare(a.name))
  } else if (sortType === 'price-low-high') {
    visible = [...visible].sort((a, b) => Number(a.price) - Number(b.price))
  } else if (sortType === 'price-high-low') {
    visible = [...visible].sort((a, b) => Number(b.price) - Number(a.price))
  }

  return (
    <div className="flex flex-col sm:flex-row gap-1 sm:gap-10 pt-10 border-t-2">
      <div className="min-w-60">
        <p onClick={() => setShowFilter(!showFilter)} className="my-2 text-xl flex items-center cursor-pointer gap-2 sm:cursor-default">
          FILTERS
          <span className={`sm:hidden text-sm transition-transform ${showFilter ? 'rotate-90' : ''}`}>&gt;</span>
        </p>

        <div className={`border border-gray-300 pl-5 py-3 mt-6 ${showFilter ? '' : 'hidden'} sm:block`}>
          <p className="mb-3 text-sm font-medium">CATEGORIES</p>
          <div className="flex flex-col gap-2 text-sm font-light text-gray-700">
            {categoryList.map((category) => (
              <label key={category} className="flex gap-2 cursor-pointer">
                <input className="w-3 accent-green-600" type="checkbox" checked={categories.includes(category)} onChange={() => toggle(category, categories, setCategories)} />
                {category}
              </label>
            ))}
          </div>
        </div>

        <div className={`border border-gray-300 pl-5 py-3 my-5 ${showFilter ? '' : 'hidden'} sm:block`}>
          <p className="mb-3 text-sm font-medium">PRICE</p>
          <div className="flex flex-col gap-2 text-sm font-light text-gray-700">
            {priceRanges.map((range) => (
              <label key={range.label} className="flex gap-2 cursor-pointer">
                <input className="w-3 accent-green-600" type="checkbox" checked={ranges.includes(range.label)} onChange={() => toggle(range.label, ranges, setRanges)} />
                {range.label}
              </label>
            ))}
          </div>
        </div>

        <div className={`flex flex-col items-start gap-3 ${showFilter ? '' : 'hidden'} sm:flex`}>
          <button onClick={applyFilters} className="bg-green-600 text-white px-8 py-2 text-sm active:bg-green-400">Apply Filters</button>
          {(categories.length > 0 || ranges.length > 0 || appliedCategories.length > 0 || appliedRanges.length > 0) && (
            <button onClick={clearFilters} className="text-sm text-green-600 underline">Clear filters</button>
          )}
        </div>
      </div>

      <div className="flex-1">
        <div className="flex justify-between items-center text-base sm:text-2xl mb-4">
          <TextContent text1={"ALL"} text2={"PRODUCTS"} />
          <select value={sortType} onChange={(e) => setSortType(e.target.value)} className="border-2 border-gray-300 text-sm px-2 py-1">
            <option value="random">Sort by: Default</option>
            <option value="name-asc">Sort by: Name A-Z</option>
            <option value="name-desc">Sort by: Name Z-A</option>
            <option value="price-low-high">Sort by: Price Low to High</option>
            <option value="price-high-low">Sort by: Price High to Low</option>
          </select>
        </div>

        {visible.length === 0 ? (
          <p className="py-16 text-center text-gray-500">No products match your filters.</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 gap-y-6">
            {visible.map((item) => (
              <StoreItem
                key={item.product_id}
                id={item.product_id}
                name={item.name}
                image={item.image}
                price={item.price}
                weight={item.unit_weight_lb}
                available={item.stock > 0}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default Products
