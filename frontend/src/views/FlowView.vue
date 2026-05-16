<script setup>
import MermaidDiagram from '../components/MermaidDiagram.vue'

const flowDiagram = `flowchart TB
    START([用户提交需求]) --> DECOMP[decompose_requirement<br/>需求预分解]
    DECOMP --> SUBS[SubRequirement[]<br/>N个子需求]

    SUBS --> CONV[卷积层: Tree-sitter AST解析<br/>+增量分析+索引构建]
    CONV --> POOL[池化层: AST增强评分排序<br/>+Hierarchical压缩]
    POOL --> FC1[FC1: 按SubRequirement逐个规划<br/>+CodeIndex查询+冲突检测]

    FC1 --> DEP{ModificationDependencyGraph<br/>依赖图构建}
    DEP --> TOPO[拓扑排序<br/>循环去重]
    TOPO --> PARALLEL[并行执行修改项<br/>dispatch_redundant()]

    PARALLEL --> CONSENSUS[ConsensusEngine<br/>语义等价共识选择]
    CONSENSUS --> APPLY[diff/patch模式应用<br/>file_state一致性]

    APPLY --> VERIFY{verify_syntax}
    VERIFY -->|成功| FC3[FC3: 测试生成<br/>+token感知截断]
    VERIFY -->|失败| ROLLBACK[_rollback_failed_files<br/>恢复备份]
    ROLLBACK --> RETRY{重试次数<3?}
    RETRY -->|是| APPLY
    RETRY -->|否| FAIL([标记失败])

    FC3 --> INTEGRITY[_check_modification_integrity<br/>完整性校验+冲突摘要]
    INTEGRITY --> OUTPUT([最终输出<br/>修改+测试+验证结果])

    OUTPUT --> STM[短期记忆写入<br/>5层结果]
    OUTPUT --> LTM[长期记忆写入<br/>save_task_experience]
    OUTPUT --> FEEDBACK[等待用户反馈]

    FEEDBACK --> BP[反向传播<br/>reward→trust更新]
    BP --> PERSIST[_persist_trust_updates<br/>DB+STM+LTM趋势]
    PERSIST --> START

    style START fill:#06b6d4,stroke:#06b6d4,color:#fff
    style FAIL fill:#ef4444,stroke:#ef4444,color:#fff
    style OUTPUT fill:#10b981,stroke:#10b981,color:#fff
    style VERIFY fill:#f59e0b,stroke:#f59e0b,color:#fff
    style RETRY fill:#f59e0b,stroke:#f59e0b,color:#fff`
</script>

<template>
  <div>
    <div class="page-header">
      <el-icon :size="24" color="var(--accent-green)"><Guide /></el-icon>
      <h2>需求处理流程图</h2>
      <el-tag type="success" size="small" style="margin-left:auto;">含4层合并防线</el-tag>
    </div>
    <MermaidDiagram :definition="flowDiagram" />
  </div>
</template>
