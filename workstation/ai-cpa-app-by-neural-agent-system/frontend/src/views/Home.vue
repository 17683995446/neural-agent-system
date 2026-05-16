<template>
  <div class="home-page">
    <section class="hero">
      <div class="hero-content">
        <h1>AI赋能 CPA备考</h1>
        <p class="hero-subtitle">基于AI智能诊断、个性化学习路径、精准题库推荐，让您的注册会计师备考事半功倍</p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="handleStart">立即开始</el-button>
          <el-button size="large" @click="$router.push('/diagnosis')">AI诊断测评</el-button>
        </div>
        <div class="hero-stats">
          <div class="stat"><strong>10万+</strong><span>精选题目</span></div>
          <div class="stat"><strong>6科</strong><span>全科覆盖</span></div>
          <div class="stat"><strong>AI</strong><span>智能诊断</span></div>
          <div class="stat"><strong>98%</strong><span>学员好评</span></div>
        </div>
      </div>
    </section>

    <section class="features page-container">
      <h2 class="section-title">AI智能学习体系</h2>
      <div class="card-grid card-grid-4 features-grid">
        <el-card v-for="f in features" :key="f.title" shadow="hover" class="feature-card">
          <div class="feature-icon">{{ f.icon }}</div>
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
        </el-card>
      </div>
    </section>

    <section class="subjects page-container">
      <h2 class="section-title">CPA六科全覆盖</h2>
      <div class="card-grid card-grid-3 subjects-grid">
        <el-card v-for="s in subjects" :key="s.key" shadow="hover" class="subject-card" :class="'subject-bg-' + s.key" @click="goSubject(s.key)">
          <div class="subject-icon">{{ s.icon }}</div>
          <h3>{{ s.name }}</h3>
          <p>{{ s.desc }}</p>
          <div class="subject-stats">
            <span>{{ s.count }}题</span>
            <el-progress :percentage="s.mastery" :stroke-width="6" :color="s.color" />
          </div>
        </el-card>
      </div>
    </section>

    <section class="cta">
      <div class="cta-content page-container">
        <h2>开启您的CPA智能备考之旅</h2>
        <p>AI诊断 → 个性化计划 → 智能刷题 → 机考模拟 → 稳步通关</p>
        <el-button type="primary" size="large" @click="handleStart">免费注册，立即体验</el-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

const features = [
  { icon: '🧠', title: 'AI诊断', desc: '智能检测知识薄弱点，生成个性化学习画像与知识雷达图' },
  { icon: '🎯', title: '智能刷题', desc: 'AI根据薄弱点精准推荐题目，实时批改与解析，高效提分' },
  { icon: '📝', title: '机考模拟', desc: '全真模拟CPA机考环境，计时、标记、提交，提前适应考场' },
  { icon: '💬', title: 'AI答疑', desc: '24小时AI答疑助手，CPA专业语境理解，随时解决学习疑问' }
]

const subjects = [
  { key: 'accounting', name: '会计', icon: '📊', desc: '长期股权投资、合并报表、收入准则等核心考点', count: 25000, mastery: 0, color: '#1890ff' },
  { key: 'audit', name: '审计', icon: '🔍', desc: '审计程序、审计证据、审计报告等理论实务', count: 18000, mastery: 0, color: '#722ed1' },
  { key: 'fm', name: '财管', icon: '📈', desc: '财务分析、资本预算、期权定价等计算分析', count: 15000, mastery: 0, color: '#13c2c2' },
  { key: 'ecl', name: '经济法', icon: '⚖️', desc: '公司法、证券法、合同法等法律法规', count: 12000, mastery: 0, color: '#eb2f96' },
  { key: 'tax', name: '税法', icon: '💰', desc: '增值税、企业所得税、个税等税收政策', count: 16000, mastery: 0, color: '#fa8c16' },
  { key: 'strategy', name: '战略', icon: '🎯', desc: '战略分析、战略选择、风险管理等综合应用', count: 8000, mastery: 0, color: '#52c41a' }
]

const handleStart = () => {
  if (userStore.isLoggedIn) router.push('/dashboard')
  else router.push('/register')
}

const goSubject = (key) => {
  if (userStore.isLoggedIn) router.push({ path: '/questions', query: { subject: key } })
  else router.push('/login')
}
</script>

<style scoped>
.hero {
  background: linear-gradient(135deg, #001529 0%, #096dd9 100%);
  color: #fff;
  padding: 80px 20px;
  text-align: center;
}
.hero h1 { font-size: 48px; font-weight: 700; margin-bottom: 16px; }
.hero-subtitle { font-size: 18px; opacity: 0.85; max-width: 600px; margin: 0 auto 32px; }
.hero-actions { display: flex; gap: 16px; justify-content: center; margin-bottom: 48px; }
.hero-stats { display: flex; justify-content: center; gap: 48px; }
.hero-stats .stat { text-align: center; }
.hero-stats strong { display: block; font-size: 32px; color: #faad14; }
.hero-stats span { font-size: 14px; opacity: 0.8; }
.section-title { text-align: center; font-size: 28px; font-weight: 600; margin-bottom: 32px; }
.features, .subjects { padding: 60px 20px; }
.feature-card { text-align: center; padding: 20px; cursor: pointer; transition: transform 0.3s; }
.feature-card:hover { transform: translateY(-4px); }
.feature-icon { font-size: 48px; margin-bottom: 12px; }
.feature-card h3 { font-size: 18px; margin-bottom: 8px; color: var(--cpa-text); }
.feature-card p { font-size: 14px; color: var(--cpa-text-secondary); line-height: 1.6; }
.subject-card { cursor: pointer; transition: transform 0.3s; }
.subject-card:hover { transform: translateY(-4px); }
.subject-icon { font-size: 36px; margin-bottom: 8px; }
.subject-card h3 { font-size: 18px; margin-bottom: 6px; }
.subject-card p { font-size: 13px; color: var(--cpa-text-secondary); line-height: 1.5; margin-bottom: 12px; }
.subject-stats { font-size: 12px; color: var(--cpa-text-secondary); }
.subject-stats span { margin-right: 8px; }
.cta { background: linear-gradient(135deg, #096dd9, #001529); color: #fff; padding: 60px 20px; text-align: center; }
.cta h2 { font-size: 28px; margin-bottom: 12px; }
.cta p { font-size: 16px; opacity: 0.85; margin-bottom: 24px; }
@media (max-width: 768px) {
  .hero h1 { font-size: 32px; }
  .hero-stats { gap: 24px; }
  .hero-stats strong { font-size: 24px; }
}
</style>
