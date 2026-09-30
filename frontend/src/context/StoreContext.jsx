import { createContext, useState } from 'react'
import { products } from '../assets/assets'

export const StoreContext = createContext()

const StoreContextProvider = (props) => {

    const currency = '$'
    const [shoppingCartItems, setShoppingCartItems] = useState({})

    const addToCart = (itemId) => {
        const item = products.find((product) => product.product_id === itemId)
        if (!item) return

        setShoppingCartItems((previous) => {
            const current = previous[itemId] || 0
            if (current >= item.stock) return previous
            return { ...previous, [itemId]: current + 1 }
        })
    }

    const getShoppingCartCount = () => {
        let total = 0
        for (const itemId in shoppingCartItems) {
            total += shoppingCartItems[itemId]
        }
        return total
    }

    const value = {
        products,
        currency,
        shoppingCartItems,
        addToCart,
        getShoppingCartCount,
    }

    return (
        <StoreContext.Provider value={value}>
            {props.children}
        </StoreContext.Provider>
    )
}

export default StoreContextProvider
