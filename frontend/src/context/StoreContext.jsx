import { createContext, useCallback, useEffect, useState } from 'react'
import { assets } from '../assets/assets'
import { api } from '../api'

export const StoreContext = createContext()

// Shown for products added by staff that have no matching image file.
const placeholderImage =
    'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1" fill="%23e5e7eb"/></svg>'

// The backend names each product's picture (image_key); the files live in
// src/assets, so the frontend turns the name into the bundled image.
const withImage = (product) => ({ ...product, image: assets[product.image_key] || placeholderImage })

const emptyCart = {
    items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00',
    delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false,
}

const StoreContextProvider = (props) => {

    const currency = '$'
    const [products, setProducts] = useState([])
    const [productsError, setProductsError] = useState('')
    const [productsLoading, setProductsLoading] = useState(true)
    const [cart, setCart] = useState(emptyCart)

    const loadProducts = useCallback(async () => {
        try {
            const data = await api('/api/products')
            setProducts(data.products.map(withImage))
            setProductsError('')
        } catch (error) {
            setProductsError(error.message)
        } finally {
            setProductsLoading(false)
        }
    }, [])

    const loadCart = useCallback(async () => {
        try {
            const data = await api('/api/cart')
            setCart(data.cart)
        } catch {
            setCart(emptyCart)      // e.g. staff accounts have no cart
        }
    }, [])

    useEffect(() => {
        loadProducts()
        loadCart()
    }, [loadProducts, loadCart])

    // The backend checks stock and returns the whole repriced cart after
    // every change. These return {ok, message} so pages can show the
    // backend's explanation when something is refused.
    const changeCart = async (path, method, body) => {
        try {
            const data = await api(path, { method, body })
            setCart(data.cart)
            return { ok: true }
        } catch (error) {
            return { ok: false, message: error.message }
        }
    }

    const addToCart = (itemId, quantity = 1) =>
        changeCart('/api/cart/items', 'POST', { product_id: itemId, quantity })

    const updateQuantity = (itemId, quantity) =>
        quantity <= 0
            ? removeFromCart(itemId)
            : changeCart(`/api/cart/items/${itemId}`, 'PATCH', { quantity })

    const removeFromCart = (itemId) => changeCart(`/api/cart/items/${itemId}`, 'DELETE')

    const shoppingCartItems = Object.fromEntries(cart.items.map((item) => [item.product_id, item.quantity]))

    const value = {
        products,
        productsLoading,
        productsError,
        currency,
        cart,
        cartItems: cart.items.map(withImage),
        shoppingCartItems,
        addToCart,
        updateQuantity,
        removeFromCart,
        reloadProducts: loadProducts,
        reloadCart: loadCart,
        getShoppingCartCount: () => cart.item_count,
    }

    return (
        <StoreContext.Provider value={value}>
            {props.children}
        </StoreContext.Provider>
    )
}

export default StoreContextProvider
