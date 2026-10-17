import { isNative } from '../platform/index.js'
import { authenticatedFetch as request, post } from './authenticatedFetch.js'
export const login = body => request('/auth/login', { method: 'POST', body: { ...body, client_type: isNative() ? 'native' : 'web' }, auth: false })
export const register = body => request('/auth/register', { method: 'POST', body, auth: false })
export const logout = () => post('/auth/logout')
export const getMe = () => request('/me')
export const updateProfile = display_name => request('/me', { method: 'PATCH', body: { display_name } })
export const changePassword = (current_password, new_password) => post('/auth/change-password', { current_password, new_password })
