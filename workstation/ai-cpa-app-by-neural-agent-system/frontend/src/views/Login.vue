<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2>登录 AI CPA 智能备考</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="手机号/邮箱" prop="account">
          <el-input v-model="form.account" placeholder="请输入手机号或邮箱" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" size="large" show-password>
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" :loading="loading" style="width:100%" @click="handleLogin">登录</el-button>
        </el-form-item>
      </el-form>
      <div class="auth-footer">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ account: '', password: '' })
const rules = {
  account: [{ required: true, message: '请输入手机号或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  try {
    await formRef.value.validate()
  } catch { return }
  loading.value = true
  try {
    const loginData = { password: form.password }
    if (form.account.includes('@')) {
      loginData.email = form.account
    } else {
      loginData.phone = form.account
    }
    await userStore.login(loginData)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect || '/dashboard'
    router.push(redirect)
  } catch {} finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #001529, #096dd9); }
.auth-card { background: #fff; border-radius: 12px; padding: 40px; width: 420px; max-width: 90vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.auth-card h2 { text-align: center; margin-bottom: 24px; color: var(--cpa-primary); }
.auth-footer { text-align: center; margin-top: 16px; font-size: 14px; color: var(--cpa-text-secondary); }
.auth-footer a { color: var(--cpa-primary); text-decoration: none; }
</style>
