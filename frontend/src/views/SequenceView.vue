<script setup>
import { ref } from 'vue'
import MermaidDiagram from '../components/MermaidDiagram.vue'

const showBackward = ref(false)

const forwardSeq = `sequenceDiagram
    participant U as 用户
    participant I as Layer0 输入层
    participant C as Layer1 卷积层
    participant P as Layer2 池化层
    participant F1 as Layer3 FC1
    participant F2 as Layer4 FC2
    participant F3 as Layer5 FC3
    participant O as Layer6 输出层
    participant STM as 短期记忆
    participant LTM as 长期记忆

    U->>I: 用户需求
    I->>I: decompose_requirement()
    I->>STM: save_message("input")
    I->>C: SubRequirement[]

    C->>C: Tree-sitter AST解析(9语言)
    C->>C: ASTCache.get_or_parse()
    C->>C: ChangeDetector(增量)
    C->>C: CodeStructureIndex构建
    C->>STM: save_message("conv_agent")

    C->>P: analyzed_files
    P->>P: calculate_relevance_enhanced()
    P->>P: HierarchicalCompressor(3级)
    P->>P: Top 50/50/100 排序
    P->>STM: save_message("pool_agent")

    P->>F1: compressed_features
    F1->>LTM: get_similar_experiences()
    F1->>F1: _query_code_index(继承/装饰器/跨文件)
    Note over F1: 按SubRequirement逐个规划
    F1->>F1: _merge_modification_lists(冲突检测)
    F1->>LTM: save_task_experience()
    F1->>STM: save_message("fc1_agent")

    F1->>F2: modification_list
    F2->>F2: ModificationDependencyGraph(拓扑排序)
    F2->>F2: dispatch_redundant()(3视角共识)
    F2->>F2: ConsensusEngine(语义等价)
    F2->>F2: diff/patch模式 + file_state一致性
    F2->>F2: verify_syntax(compile+tree-sitter+pytest)
    F2->>F2: _rollback_failed_files()
    F2->>STM: save_message("fc2_agent")

    F2->>F3: modifications
    F3->>F3: SmartContextWindow(token感知)
    F3->>F3: 测试代码生成
    F3->>STM: save_message("fc3_agent")

    F3->>O: results + tests + verification
    O->>U: 最终输出`

const backwardSeq = `sequenceDiagram
    participant U as 用户
    participant BP as 反向传播
    participant RC as RewardCalculator
    participant TWU as TrustWeightUpdater
    participant TM as TrustManager
    participant STM as 短期记忆
    participant LTM as 长期记忆
    participant DB as 数据库

    U->>BP: 反馈(satisfaction_score)
    BP->>RC: calculate_reward(feedback)
    RC-->>BP: reward ∈ [-1, 1]

    BP->>BP: _calculate_layer_reward(7层权重)
    Note over BP: output:0.9 fc2:0.8 fc1:0.7<br/>pool:0.6 conv:0.5 fc3:0.4 input:0.3

    BP->>TWU: update_weights(current, rewards)
    Note over TWU: learning_rate × reward<br/>clip到[0, 2]
    TWU-->>BP: new_trust_weights

    BP->>TM: update_trust_matrix()
    BP->>BP: _persist_trust_updates()
    BP->>DB: UPDATE trust_matrix
    BP->>STM: save_trust_matrix()
    BP->>LTM: save_trend(长期趋势)`
</script>

<template>
  <div>
    <div class="page-header">
      <el-icon :size="24" color="var(--accent-secondary)"><Connection /></el-icon>
      <h2>Pipeline时序图</h2>
      <el-switch v-model="showBackward" active-text="反向传播" inactive-text="正向流水线" style="margin-left:auto;" />
    </div>
    <MermaidDiagram :definition="showBackward ? backwardSeq : forwardSeq" />
  </div>
</template>
