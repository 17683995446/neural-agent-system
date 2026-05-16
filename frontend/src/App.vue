<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Share, Connection, Operation, Guide, Switch,
  DataLine, Monitor
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)

const menuItems = [
  { path: '/architecture', icon: Share, label: '架构图' },
  { path: '/sequence', icon: Connection, label: '时序图' },
  { path: '/modules', icon: Operation, label: '模块原理' },
  { path: '/flow', icon: Guide, label: '流程图' },
  { path: '/state', icon: Opened, label: '状态图' },
  { path: '/dashboard', icon: DataLine, label: '实时仪表盘' },
]

const nav = (path) => router.push(path)
</script>

<template>
  <div style="display:flex;height:100vh;">
    <el-aside :width="collapsed ? '64px' : '200px'" style="
      background:var(--bg-secondary); border-right:1px solid var(--border-color);
      display:flex; flex-direction:column; transition:width .3s;
    ">
      <div style="padding:16px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border-color);">
        <div style="width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--accent-primary),var(--accent-secondary));display:flex;align-items:center;justify-content:center;flex-shrink:0;">
          <el-icon :size="18" color="#fff"><Monitor /></el-icon>
        </div>
        <span v-if="!collapsed" style="font-size:14px;font-weight:600;color:var(--text-primary);white-space:nowrap;">Neural Agent</span>
      </div>
      <el-menu :default-active="route.path" @select="nav" style="flex:1;padding:8px 0;">
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span v-if="!collapsed">{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
      <div style="padding:12px;border-top:1px solid var(--border-color);display:flex;justify-content:center;">
        <el-button text @click="collapsed = !collapsed" style="color:var(--text-muted);">
          <el-icon><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
        </el-button>
      </div>
    </el-aside>
    <el-main style="background:var(--bg-primary);overflow-y:auto;padding:24px;">
      <router-view />
    </el-main>
  </div>
</template>
