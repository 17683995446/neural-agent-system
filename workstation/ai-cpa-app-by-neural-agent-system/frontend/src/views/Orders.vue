<template>
  <div class="page-container orders-page">
    <h1 class="page-title">💰 我的订单</h1>
    <el-card shadow="never" v-loading="loading">
      <el-table :data="orders" stripe style="width:100%">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="id" label="订单号" width="180" />
        <el-table-column prop="product_name" label="商品名称" min-width="200" />
        <el-table-column prop="amount" label="金额" width="100">
          <template #default="{ row }">¥{{ row.amount }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="下单时间" width="180">
          <template #default="{ row }">{{ row.created_at?.substring(0, 19) }}</template>
        </el-table-column>
      </el-table>
      <div v-if="orders.length === 0 && !loading" class="empty-tip">暂无订单</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api/index'

const loading = ref(false)
const orders = ref([])

const statusType = (s) => ({ paid: 'success', pending: 'warning', cancelled: 'info', refunded: 'danger' }[s] || 'info')
const statusLabel = (s) => ({ paid: '已支付', pending: '待支付', cancelled: '已取消', refunded: '已退款' }[s] || s)

onMounted(async () => {
  loading.value = true
  try { const res = await api.get('/orders'); orders.value = res.data || [] } catch {} finally { loading.value = false }
})
</script>

<style scoped>
.empty-tip { text-align: center; padding: 40px; color: var(--cpa-text-secondary); }
</style>
