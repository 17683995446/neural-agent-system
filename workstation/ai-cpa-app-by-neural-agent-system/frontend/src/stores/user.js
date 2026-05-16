import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api/auth'

let _router = null
export const setUserRouter = (router) => { _router = router }

export const useUserStore = defineStore('user', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('token') || '')

  const isLoggedIn = computed(() => !!token.value)

  const setToken = (newToken) => {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  const login = async (credentials) => {
    const res = await authApi.login(credentials)
    const tk = res.data.access_token || res.data.token
    setToken(tk)
    user.value = res.data.user
    return res.data
  }

  const register = async (data) => {
    const res = await authApi.register(data)
    const tk = res.data.access_token || res.data.token
    setToken(tk)
    user.value = res.data.user
    return res.data
  }

  const fetchProfile = async () => {
    try {
      const res = await authApi.getMe()
      user.value = res.data
    } catch {
      logout()
    }
  }

  const updateProfile = async (data) => {
    const res = await authApi.updateMe(data)
    user.value = res.data
    return res.data
  }

  const logout = () => {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    if (_router) _router.push('/')
  }

  return { user, token, isLoggedIn, login, register, fetchProfile, updateProfile, logout }
})
