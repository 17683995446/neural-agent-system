<script setup>
import { ref } from 'vue'
import MermaidDiagram from '../components/MermaidDiagram.vue'

const activeState = ref('task')

const diagrams = {
  task: {
    title: 'TaskStatus 状态机',
    def: `stateDiagram-v2
    [*] --> PENDING : 任务创建
    PENDING --> ANALYZING : 获取Agent
    ANALYZING --> PLANNING : 分析完成
    PLANNING --> EXECUTING : 规划完成
    EXECUTING --> VERIFYING : 执行完成
    VERIFYING --> ITERATING : 验证失败(重试)
    VERIFYING --> COMPLETED : 验证成功
    ITERATING --> EXECUTING : 重新执行
    ITERATING --> COMPLETED : 达到max_iteration
    EXECUTING --> FAILED : 不可恢复错误
    PLANNING --> FAILED : 规划失败
    ANALYZING --> FAILED : 分析失败

    state ITERATING {
        [*] --> RETRY
        RETRY --> EXECUTING2 : retry
        EXECUTING2 --> VERIFY2 : done
        VERIFY2 --> RETRY : fail
        VERIFY2 --> [*] : pass
    }`
  },
  circuit: {
    title: 'CircuitBreaker 状态机',
    def: `stateDiagram-v2
    [*] --> CLOSED : 初始化

    state CLOSED {
        [*] --> NORMAL
        NORMAL --> COUNTING : failure++
        COUNTING --> NORMAL : success→reset_count
        COUNTING --> TRIP : count>=threshold
    }

    CLOSED --> OPEN : failure_count>=threshold

    state OPEN {
        [*] --> BLOCKING
        BLOCKING : 所有请求→fallback
    }

    OPEN --> HALF_OPEN : recovery_timeout超时

    state HALF_OPEN {
        [*] --> PROBE
        PROBE : 放行1个探测请求
    }

    HALF_OPEN --> CLOSED : 探测成功
    HALF_OPEN --> OPEN : 探测失败`
  },
  acomplete: {
    title: 'acomplete() 请求生命周期',
    def: `stateDiagram-v2
    [*] --> CHECK_AVAILABLE : 调用acomplete()
    CHECK_AVAILABLE --> FALLBACK : 不可用
    CHECK_AVAILABLE --> CHECK_CACHE : 可用

    CHECK_CACHE --> CACHE_HIT : 缓存命中
    CHECK_CACHE --> CHECK_CIRCUIT : 缓存未命中

    CHECK_CIRCUIT --> CIRCUIT_OPEN : 熔断器OPEN
    CHECK_CIRCUIT --> ACQUIRE_RATE : 熔断器CLOSED/HALF_OPEN
    CIRCUIT_OPEN --> FALLBACK

    ACQUIRE_RATE --> RATE_TIMEOUT : acquire超时
    ACQUIRE_RATE --> DO_REQUEST : acquire成功
    RATE_TIMEOUT --> FALLBACK

    DO_REQUEST --> SUCCESS : HTTP 200
    DO_REQUEST --> RETRY : 429/500/502/503
    DO_REQUEST --> ERROR : 其他HTTP错误

    RETRY --> DO_REQUEST : 指数退避
    RETRY --> ERROR : 重试耗尽

    SUCCESS --> CACHE_PUT : 写入缓存
    CACHE_PUT --> RELEASE : rate_limiter.release()
    RELEASE --> [*]

    ERROR --> ON_FAILURE : circuit._on_failure()
    ON_FAILURE --> RELEASE2 : rate_limiter.release()
    RELEASE2 --> FALLBACK_OR_RAISE

    SUCCESS --> ON_SUCCESS : circuit._on_success()
    FALLBACK --> [*]
    FALLBACK_OR_RAISE --> [*]`
  },
}
</script>

<template>
  <div>
    <div class="page-header">
      <el-icon :size="24" color="var(--accent-pink)"><Opened /></el-icon>
      <h2>状态图</h2>
    </div>
    <el-tabs v-model="activeState" type="card" style="margin-bottom:20px;">
      <el-tab-pane v-for="(v,k) in diagrams" :key="k" :label="v.title" :name="k" />
    </el-tabs>
    <MermaidDiagram :definition="diagrams[activeState].def" />
  </div>
</template>
