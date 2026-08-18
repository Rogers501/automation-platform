<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getExecutions, getReport, type ExecutionRecord, type Report } from '../api'
import { useProjectStore } from '../stores/project'

const store = useProjectStore()
const executions = ref<ExecutionRecord[]>([])
const reports = ref<Record<string, Report>>({})

const totalCases = computed(() => store.projects.reduce((sum, item) => sum + item.case_count, 0))

const health = computed(() => {
  const list = Object.values(reports.value).filter((item) => item.total > 0)
  const passed = list.reduce((sum, item) => sum + item.passed, 0)
  const total = list.reduce((sum, item) => sum + item.total, 0)
  return total === 0 ? 0 : Math.round((passed / total) * 1000) / 10
})

onMounted(async () => {
  await store.loadProjects()
  const [{ data }] = await Promise.all([getExecutions()])
  executions.value = data.slice(0, 8)
  await Promise.all(
    store.projects.map(async (project) => {
      const { data: report } = await getReport(project.name)
      reports.value[project.name] = report
    }),
  )
})
</script>

<template>
  <div>
    <div class="metric-grid">
      <div class="panel metric">
        <span class="metric-label">测试项目</span>
        <strong>{{ store.projects.length }}</strong>
      </div>
      <div class="panel metric">
        <span class="metric-label">测试文件</span>
        <strong>{{ totalCases }}</strong>
      </div>
      <div class="panel metric">
        <span class="metric-label">报告通过率</span>
        <strong :class="health >= 90 ? 'ok' : health >= 70 ? 'warn' : 'bad'">{{ health }}%</strong>
      </div>
      <div class="panel metric">
        <span class="metric-label">最近执行</span>
        <strong>{{ executions.length }}</strong>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="panel">
        <h3>项目概览</h3>
        <el-table :data="store.projects" height="430">
          <el-table-column prop="name" label="项目" min-width="110" />
          <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="环境" min-width="120">
            <template #default="{ row }">
              <el-tag v-for="env in row.envs" :key="env" size="small" class="env-tag">{{ env }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="case_count" label="文件数" width="80" />
        </el-table>
      </div>

      <div class="panel">
        <h3>最近执行</h3>
        <el-table :data="executions" height="430">
          <el-table-column prop="project" label="项目" width="90" />
          <el-table-column prop="env" label="环境" width="70" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'passed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="started_at" label="开始时间" min-width="160" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
  margin-top: 16px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric strong {
  font-size: 28px;
}

.metric-label {
  color: #687385;
  font-size: 13px;
}

h3 {
  margin: 0 0 14px;
  font-size: 15px;
}

.ok { color: #208154; }
.warn { color: #a36611; }
.bad { color: #c5342a; }
.env-tag { margin-right: 4px; }

@media (max-width: 1100px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .dashboard-grid { grid-template-columns: 1fr; }
}
</style>
