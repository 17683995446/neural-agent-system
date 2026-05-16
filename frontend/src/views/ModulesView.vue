<script setup>
import { ref } from 'vue'
import MermaidDiagram from '../components/MermaidDiagram.vue'

const activeModule = ref('conv')

const modules = {
  conv: {
    title: 'Layer 1: 卷积层 — 代码特征提取',
    diagram: `flowchart LR
    subgraph INPUT["输入"]
        SRC["源文件<br/>.py/.js/.ts/.java<br/>.go/.rs/.c/.cpp/.rb"]
    end
    subgraph PARSE["Tree-sitter AST解析"]
        L14["Language v14 Grammar"]
        FN["_FUNCTION_NODES<br/>9种语言函数节点"]
        CL["_CLASS_NODES<br/>9种语言类节点"]
        IM["_IMPORT_NODES<br/>9种语言导入节点"]
    end
    subgraph CACHE["ASTCache"]
        LRU["LRU淘汰<br/>max_memory"]
        DISK["磁盘持久化<br/>safe_pickle"]
        MTIME["mtime变更检测<br/>→自动重解析"]
    end
    subgraph INCREMENTAL["增量分析"]
        CD["ChangeDetector<br/>_build_call_graph"]
        IDX["CodeStructureIndex<br/>SQLite WAL 6表"]
    end
    SRC --> L14 --> FN & CL & IM
    L14 --> LRU --> DISK --> MTIME
    MTIME --> CD --> IDX`
  },
  pool: {
    title: 'Layer 2: 池化层 — 信息压缩',
    diagram: `flowchart LR
    subgraph INPUT["输入"]
        FILES["analyzed_files<br/>全量AST结果"]
    end
    subgraph SCORE["评分"]
        KW["extract_keywords()<br/>停用词过滤"]
        REL["calculate_relevance_enhanced()<br/>函数名+类名+imports<br/>+summary+file_path"]
    end
    subgraph COMPRESS["HierarchicalCompressor"]
        MOD["模块摘要<br/>max_module_summaries"]
        FILE["文件摘要<br/>max_file_summaries"]
        FUNC["函数详情<br/>max_function_details"]
    end
    subgraph OUTPUT["输出"]
        TOP["Top 50/50/100<br/>按相关性排序"]
    end
    FILES --> KW --> REL --> MOD & FILE & FUNC --> TOP`
  },
  fc1: {
    title: 'Layer 3: FC1全局理解层',
    diagram: `flowchart LR
    subgraph INPUT["输入"]
        SUB["SubRequirement[]<br/>需求预分解"]
        CTX["compressed_features"]
    end
    subgraph CONTEXT["上下文构建"]
        SCW["SmartContextWindow<br/>12K字符"]
        CI["_query_code_index()<br/>继承+装饰器+跨文件调用"]
        LTM["长期记忆<br/>get_similar_experiences()"]
    end
    subgraph PLAN["规划"]
        PER_SUB["按SubRequirement逐个规划"]
        MERGE["_merge_modification_lists<br/>区域级冲突检测"]
    end
    subgraph SAVE["持久化"]
        EXP["save_task_experience()<br/>长期记忆写入"]
    end
    SUB --> SCW & CI & LTM
    CTX --> SCW
    SCW --> PER_SUB --> MERGE --> EXP`
  },
  fc2: {
    title: 'Layer 4: FC2代码生成层',
    diagram: `flowchart LR
    subgraph DEP["依赖分析"]
        GRAPH["ModificationDependencyGraph<br/>调用图+imports"]
        TOPO["_topological_sort<br/>循环去重"]
    end
    subgraph CONSENSUS["多Agent共识"]
        DISPATCH["dispatch_redundant()<br/>3种prompt变体"]
        ENGINE["ConsensusEngine<br/>4策略: strict/normalized<br/>/overlap/structure"]
    end
    subgraph APPLY["应用修改"]
        DIFF["diff/patch模式<br/>file_state一致性"]
    end
    subgraph VERIFY["验证"]
        COMPILE["compile()+tree-sitter"]
        PYTEST["pytest执行"]
        ROLLBACK["_rollback_failed_files()"]
    end
    GRAPH --> TOPO --> DISPATCH --> ENGINE --> DIFF --> COMPILE --> PYTEST --> ROLLBACK`
  },
  trust: {
    title: '信任度管理 + 反向传播',
    diagram: `flowchart LR
    subgraph FEEDBACK["反馈输入"]
        SCORE["satisfaction_score<br/>1-5分"]
        ITEMS["feedback_items<br/>positive/negative/critical"]
    end
    subgraph REWARD["奖励计算"]
        RC["RewardCalculator<br/>score→reward∈[-1,1]"]
        CLAMP["裁剪到[-1,1]"]
    end
    subgraph LAYER["层奖励"]
        LW["7层权重<br/>output:0.9 fc2:0.8 fc1:0.7<br/>pool:0.6 conv:0.5 fc3:0.4"]
    end
    subgraph UPDATE["权重更新"]
        TWU["TrustWeightUpdater<br/>lr×reward, clip_param"]
        BOUNDS["边界约束[0, 2]"]
    end
    subgraph PERSIST["持久化"]
        DB["UPDATE trust_matrix"]
        STM["短期记忆"]
        LTM["长期趋势"]
    end
    SCORE & ITEMS --> RC --> CLAMP --> LW --> TWU --> BOUNDS --> DB & STM & LTM`
  },
  infra: {
    title: '基础设施层 — 限频/熔断/缓存/安全',
    diagram: `flowchart LR
    subgraph RATE["限频"]
        SEM["Semaphore<br/>max_concurrent"]
        BUCKET["令牌桶<br/>max_qps"]
        ACQ["acquire(timeout)<br/>阻塞/超时"]
    end
    subgraph CIRCUIT["熔断"]
        CLOSED["CLOSED<br/>正常请求"]
        OPEN["OPEN<br/>直接fallback"]
        HALF["HALF_OPEN<br/>探测1个请求"]
    end
    subgraph CACHE["缓存"]
        LRU["LRU淘汰<br/>max_size"]
        TTL["TTL过期<br/>ttl_seconds"]
        HIT["cache.get()<br/>hit/miss统计"]
    end
    subgraph SEC["安全"]
        HMAC["SafePickle<br/>HMAC-SHA256"]
        TV["路径遍历防护<br/>HTTPException(400)"]
    end
    SEM & BUCKET --> ACQ
    CLOSED -->|failure_threshold| OPEN -->|recovery_timeout| HALF -->|success| CLOSED
    HALF -->|failure| OPEN
    LRU & TTL --> HIT
    HMAC & TV`
  },
}

const moduleKeys = Object.keys(modules)
</script>

<template>
  <div>
    <div class="page-header">
      <el-icon :size="24" color="var(--accent-amber)"><Operation /></el-icon>
      <h2>模块原理图</h2>
    </div>
    <el-tabs v-model="activeModule" type="card" style="margin-bottom:20px;">
      <el-tab-pane v-for="k in moduleKeys" :key="k" :label="modules[k].title" :name="k" />
    </el-tabs>
    <MermaidDiagram :definition="modules[activeModule].diagram" />
  </div>
</template>
