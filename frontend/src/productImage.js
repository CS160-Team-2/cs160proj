import { assets } from './assets/assets'
import { API_BASE } from './api'

const placeholderImage =
    'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1" fill="%23e5e7eb"/></svg>'

const uploadPrefix = 'upload:'

export const imageFor = (imageKey) => {
    if (imageKey && imageKey.startsWith(uploadPrefix)) {
        return `${API_BASE}/api/product-images/${imageKey.slice(uploadPrefix.length)}`
    }
    return assets[imageKey] || placeholderImage
}
