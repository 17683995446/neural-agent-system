<template>
  <div class="auth-page">
    <div class="auth-card wide">
      <h2>注册 AI CPA 智能备考</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="昵称" prop="nickname">
              <el-input v-model="form.nickname" placeholder="您的昵称" size="large" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" placeholder="手机号" size="large" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="邮箱地址" size="large" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input v-model="form.password" type="password" placeholder="设置密码" size="large" show-password />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="确认密码" prop="password2">
              <el-input v-model="form.password2" type="password" placeholder="确认密码" size="large" show-password />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备考科目">
          <el-checkbox-group v-model="form.subjects">
            <el-checkbox v-for="s in subjectList" :key="s.key" :value="s.key" :label="s.name" />
          </el-checkbox-group>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="备考阶段">
              <el-select v-model="form.level" placeholder="选择阶段" size="large" style="width:100%">
                <el-option label="零基础" value="beginner" />
                <el-option label="有基础" value="intermediate" />
                <el-option label="冲刺" value="advanced" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="每日学习时长">
              <el-select v-model="form.study_hours" placeholder="选择时长" size="large" style="width:100%">
                <el-option label="1-2小时" value="1-2" />
                <el-option label="2-4小时" value="2-4" />
                <el-option label="4-6小时" value="4-6" />
                <el-option label="6小时以上" value="6+" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" size="large" :loading="loading" style="width:100%" @click="handleRegister">注册</el-button>
        </el-form-item>
      </el-form>
      <div class="auth-footer">
        已有账号？<router-link to="/login">立即登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref()
const loading = ref(false)

const subjectList = [
  { key: 'accounting', name: '会计' },
  { key: 'audit', name: '审计' },
  { key: 'fm', name: '财管' },
  { key: 'ecl', name: '经济法' },
  { key: 'tax', name: '税法' },
  { key: 'strategy', name: '战略' }
]

const form = reactive({ nickname: '', phone: '', email: '', password: '', password2: '', subjects: [], level: '', study_hours: '' })

const validatePass2 = (rule, value, callback) => {
  if (value !== form.password) callback(new Error('两次密码不一致'))
  else callback()
}

const rules = {
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  phone: [{ required: true, message: '请输入手机号', trigger: 'blur' }],
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [{ required: true, message: '请设置密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }],
  password2: [{ required: true, message: '请确认密码', trigger: 'blur' }, { validator: validatePass2, trigger: 'blur' }]
}

const subjectMap = {
  accounting: '会计', audit: '审计', fm: '财管', ecl: '经济法', tax: '税法', strategy: '战略'
}

const handleRegister = async () => {
  try {
    await formRef.value.validate()
  } catch { return }
  loading.value = true
  try {
    const submitData = {
      ...form,
      subjects: form.subjects.map(k => subjectMap[k] || k),
      study_hours: parseFloat(String(form.study_hours).replace(/[^0-9.]/g, '')) || 2
    }
    delete submitData.password2
    await userStore.register(submitData)
    ElMessage.success('注册成功')
    router.push('/diagnosis')
  } catch {} finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #001529, #096dd9); padding: 20px; }
.auth-card { background: #fff; border-radius: 12px; padding: 40px; width: 420px; max-width: 90vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.auth-card.wide { width: 600px; }
.auth-card h2 { text-align: center; margin-bottom: 24px; color: var(--cpa-primary); }
.auth-footer { text-align: center; margin-top: 16px; font-size: 14px; color: var(--cpa-text-secondary); }
.auth-footer a { color: var(--cpa-primary); text-decoration: none; }
</style>
