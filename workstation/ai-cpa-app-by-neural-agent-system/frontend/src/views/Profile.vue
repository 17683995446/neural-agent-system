<template>
  <div class="page-container profile-page">
    <h1 class="page-title">👤 个人中心</h1>
    <el-row :gutter="20">
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="avatar-card">
          <div class="avatar-section">
            <el-avatar :size="80" class="big-avatar">{{ user?.nickname?.charAt(0) || '用' }}</el-avatar>
            <h3>{{ user?.nickname || '用户' }}</h3>
            <p>{{ user?.email }}</p>
          </div>
          <div class="user-stats">
            <div class="u-stat"><strong>{{ user?.total_questions || 0 }}</strong><span>已做题目</span></div>
            <div class="u-stat"><strong>{{ user?.accuracy ? (user.accuracy * 100).toFixed(1) + '%' : '0%' }}</strong><span>正确率</span></div>
            <div class="u-stat"><strong>{{ user?.study_hours || 0 }}h</strong><span>学习时长</span></div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="16">
        <el-card shadow="hover">
          <template #header><span>编辑资料</span></template>
          <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
            <el-form-item label="昵称" prop="nickname">
              <el-input v-model="form.nickname" />
            </el-form-item>
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="form.email" />
            </el-form-item>
            <el-form-item label="备考科目">
              <el-checkbox-group v-model="form.subjects">
                <el-checkbox v-for="s in subjectList" :key="s.key" :value="s.key" :label="s.name" />
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="备考阶段">
              <el-select v-model="form.level" placeholder="选择阶段" style="width:200px">
                <el-option label="零基础" value="beginner" />
                <el-option label="有基础" value="intermediate" />
                <el-option label="冲刺" value="advanced" />
              </el-select>
            </el-form-item>
            <el-form-item label="每日学习">
              <el-select v-model="form.study_hours" placeholder="选择时长" style="width:200px">
                <el-option label="1-2小时" value="1-2" />
                <el-option label="2-4小时" value="2-4" />
                <el-option label="4-6小时" value="4-6" />
                <el-option label="6小时以上" value="6+" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleSave" :loading="saving">保存修改</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useUserStore } from '../stores/user'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const user = ref(null)
const formRef = ref()
const saving = ref(false)

const subjectList = [
  { key: 'accounting', name: '会计' }, { key: 'audit', name: '审计' }, { key: 'fm', name: '财管' },
  { key: 'ecl', name: '经济法' }, { key: 'tax', name: '税法' }, { key: 'strategy', name: '战略' }
]

const form = reactive({ nickname: '', phone: '', email: '', subjects: [], level: '', study_hours: '' })
const rules = {
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }]
}

const handleSave = async () => {
  try {
    await formRef.value.validate()
  } catch { return }
  saving.value = true
  try {
    await userStore.updateProfile(form)
    ElMessage.success('保存成功')
    user.value = userStore.user
  } catch {} finally { saving.value = false }
}

onMounted(async () => {
  await userStore.fetchProfile()
  user.value = userStore.user
  if (user.value) {
    form.nickname = user.value.nickname || ''
    form.phone = user.value.phone || ''
    form.email = user.value.email || ''
    form.subjects = user.value.subjects || []
    form.level = user.value.level || ''
    form.study_hours = user.value.study_hours || ''
  }
})
</script>

<style scoped>
.avatar-card { text-align: center; }
.avatar-section { padding: 20px 0; }
.big-avatar { background: var(--cpa-primary); color: #fff; font-size: 32px; }
.avatar-section h3 { margin-top: 12px; }
.avatar-section p { font-size: 13px; color: var(--cpa-text-secondary); }
.user-stats { display: flex; justify-content: space-around; padding: 16px 0; border-top: 1px solid #f0f0f0; }
.u-stat { text-align: center; }
.u-stat strong { display: block; font-size: 20px; color: var(--cpa-primary); }
.u-stat span { font-size: 12px; color: var(--cpa-text-secondary); }
</style>
