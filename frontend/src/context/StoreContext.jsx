import { createContext, useState } from 'react'
import { products } from '../assets/assets'

export const StoreContext = createContext()

const StoreContextProvider = (props) => {

    const currency = '$'
    const [shoppingCartItems, setShoppingCartItems] = useState({})

    const addToCart = (itemId, quantity = 1) => {
        const item = products.find((product) => product.product_id === itemId)
        if (!item) return 0

        const current = shoppingCartItems[itemId] || 0
        const added = Math.min(quantity, item.stock - current)
        if (added <= 0) return 0

        setShoppingCartItems((previous) => ({ ...previous, [itemId]: current + added }))
        return added
    }

    const updateQuantity = (itemId, quantity) => {
        const item = products.find((product) => product.product_id === itemId)
        if (!item) return

        setShoppingCartItems((previous) => {
            const next = { ...previous }
            if (quantity <= 0) {
                delete next[itemId]
            } else {
                next[itemId] = Math.min(quantity, item.stock)
            }
            return next
        })
    }

    const removeFromCart = (itemId) => updateQuantity(itemId, 0)

    const getShoppingCartCount = () => {
        let total = 0
        for (const itemId in shoppingCartItems) {
            total += shoppingCartItems[itemId]
        }
        return total
    }

    const getCartAmount = () => {
        let cents = 0
        for (const itemId in shoppingCartItems) {
            const item = products.find((product) => String(product.product_id) === itemId)
            if (item) cents += Math.round(Number(item.price) * 100) * shoppingCartItems[itemId]
        }
        return cents / 100
    }

    const getCartWeight = () => {
        let hundredths = 0
        for (const itemId in shoppingCartItems) {
            const item = products.find((product) => String(product.product_id) === itemId)
            if (item) hundredths += Math.round(Number(item.unit_weight_lb) * 100) * shoppingCartItems[itemId]
        }
        return hundredths / 100
    }

    const getDeliveryFee = () => (getCartWeight() >= 20 ? 10 : 0)

    const value = {
        products,
        currency,
        shoppingCartItems,
        addToCart,
        updateQuantity,
        removeFromCart,
        getShoppingCartCount,
        getCartAmount,
        getCartWeight,
        getDeliveryFee,
    }

    return (
        <StoreContext.Provider value={value}>
            {props.children}
        </StoreContext.Provider>
    )
}

export default StoreContextProvider
