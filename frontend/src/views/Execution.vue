<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { getCases, getExecutions, startExecution, type ExecutionRecord, type TestCase } from '../api'
import { useProjectStore } from '../stores/project'

const store = useProjectStore()
const state = reactive({ project: '', env: '' })
const cases = ref<TestCase[]>([])
const selected = ref<string[]>([])
const records = ref<ExecutionRecord[]>([])
const currentId = ref('')
const running = ref(false)
const logs = ref<string[]>([])
const consoleRef = ref<HTMLDivElement>()
let socket: WebSocket | null = null

const selectedPaths = computed(() => {
  const files = new Set(selected.value)
  return cases.value.filter((item) => files.has(item.id)).map((item) => item.file)
})

async function loadCases() {
  if (!state.project || !state.env) return
  const { data } = await getCases(state.project, state.env)
  cases.value = data.cases
  selected.value = []
}

async function loadRecords() {
  const { data } = await getExecutions()
  records.value = data
}

function onSelectionChange(rows: TestCase[]) {
  selected.value = rows.map((row) => row.id)
}

async function execute() {
  if (!state.project || !state.env) return
  const paths = selectedPaths.value.length ? Array.from(new Set(selectedPaths.value)) : ['testcase/']
  const { data } = await startExecution({ project: state.project, env: state.env, test_paths: paths })
  currentId.value = data.execution_id
  running.value = true
  logs.value = [`任务已创建：${data.execution_id}`]
  connect(data.execution_id)
  await loadRecords()
}

function connect(executionId: string) {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${protocol}://${location.host}/ws/executions/${executionId}`)
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data) as { event: string; line?: string; status?: string; cmd?: string }
    if (message.cmd) logs.value.push(message.cmd)
    if (message.line) logs.value.push(message.line)
    if (message.event === 'finished') logs.value.push(`执行结束：${message.status}`)
    if (message.event === 'finished' || message.event === 'done') {
      running.value = false
      loadRecords()
    }
    nextTick(() => consoleRef.value?.scrollTo({ top: consoleRef.value.scrollHeight }))
  }
  socket.onclose = () => { running.value = false }
}

onMounted(async () => {
  await store.loadProjects()
  const first = store.projects[0]
  if (first) {
    state.project = first.name
    state.env = first.envs[0] ?? 'test'
  }
  await Promise.all([loadCases(), loadRecords()])
})

watch(() => [state.project, state.env], loadCases)
onBeforeUnmount(() => socket?.close())
</script>

<template>
  <div class="execution-grid">
    <div>
      <div class="panel toolbar">
        <el-select v-model="state.project" filterable placeholder="选择项目" style="width: 170px">
          <el-option v-for="item in store.projects" :key="item.name" :label="item.name" :value="item.name" />
        </el-select>
        <el-select v-model="state.env" placeholder="选择环境" style="width: 120px">
          <el-option v-for="item in store.projects.find(p => p.name === state.project)?.envs ?? ['test']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-button type="primary" :loading="running" @click="execute">执行测试</el-button>
      </div>

      <div class="panel">
        <el-table :data="cases" height="580" row-key="id" @selection-change="onSelectionChange">
          <el-table-column type="selection" width="46" />
          <el-table-column prop="name" label="用例" min-width="170" />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column prop="file" label="文件" min-width="170" />
        </el-table>
      </div>
    </div>

    <div class="right-column">
      <div class="panel">
        <h3>执行控制台</h3>
        <div ref="consoleRef" class="console">
          <p v-if="logs.length === 0" class="muted">执行后这里会实时显示 pytest 输出。</p>
          <p v-for="(line, index) in logs" :key="index" class="mono">{{ line }}</p>
        </div>
      </div>

      <div class="panel">
        <h3>本次服务运行记录</h3>
        <el-table :data="records.slice(0, 12)" height="260">
          <el-table-column prop="project" label="项目" width="90" />
          <el-table-column prop="env" label="环境" width="70" />
          <el-table-column label="状态" width="85">
            <template #default="{ row }">
              <el-tag :type="row.status === 'passed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="started_at" label="开始时间" min-width="150" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.execution-grid { display: grid; grid-template-columns: 1.35fr 1fr; gap: 16px; }
.right-column { display: flex; flex-direction: column; gap: 16px; }
h3 { margin: 0 0 12px; font-size: 15px; }
.console { height: 300px; padding: 10px; overflow: auto; background: #17212b; border-radius: 6px; }
.console p { margin: 0 0 3px; color: #d8e1ea; font-size: 12px; }
@media (max-width: 1100px) { .execution-grid { grid-template-columns: 1fr; } }
</style>
