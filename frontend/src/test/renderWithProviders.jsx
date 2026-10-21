import React from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StoreContextProvider from '../context/StoreContext'

export const renderWithProviders = (ui, { route = '/' } = {}) =>
{
  return render(
    <MemoryRouter initialEntries={[route]}>
      <StoreContextProvider>
        {ui}
      </StoreContextProvider>
    </MemoryRouter>
  )
}