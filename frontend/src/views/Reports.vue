<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getReport, type Report } from '../api'
import { useProjectStore } from '../stores/project'

const store = useProjectStore()
const project = ref('')
const report = ref<Report>()
const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

const passRate = computed(() => {
  if (!report.value || report.value.total === 0) return 0
  return Math.round((report.value.passed / report.value.total) * 1000) / 10
})

async function loadReport() {
  if (!project.value) return
  const { data } = await getReport(project.value)
  report.value = data
  await nextTick()
  renderChart()
}

function renderChart() {
  if (!chartRef.value || !report.value) return
  chart ??= echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['58%', '76%'],
      label: { formatter: '{b}\n{c}' },
      data: [
        { name: '通过', value: report.value.passed, itemStyle: { color: '#208154' } },
        { name: '失败', value: report.value.failed, itemStyle: { color: '#c5342a' } },
        { name: '异常', value: report.value.broken, itemStyle: { color: '#a36611' } },
        { name: '跳过', value: report.value.skipped, itemStyle: { color: '#6b7280' } },
      ].filter((item) => item.value > 0),
    }],
  })
}

onMounted(async () => {
  await store.loadProjects()
  project.value = store.projects[0]?.name ?? ''
  await loadReport()
  window.addEventListener('resize', renderChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', renderChart)
  chart?.dispose()
})
watch(project, loadReport)
</script>

<template>
  <div>
    <div class="panel toolbar">
      <el-select v-model="project" filterable placeholder="选择项目" style="width: 180px">
        <el-option v-for="item in store.projects" :key="item.name" :label="item.name" :value="item.name" />
      </el-select>
      <span class="muted">数据来源：项目的 allure-results 目录</span>
      <el-button @click="loadReport">刷新</el-button>
    </div>

    <div class="report-grid">
      <div class="panel">
        <h3>结果分布</h3>
        <div v-if="report && report.total" ref="chartRef" class="chart"></div>
        <el-empty v-else description="暂无报告数据" />
      </div>

      <div class="panel">
        <h3>执行统计</h3>
        <div v-if="report?.total" class="stats">
          <div><span>用例总数</span><strong>{{ report.total }}</strong></div>
          <div><span>通过</span><strong class="ok">{{ report.passed }}</strong></div>
          <div><span>失败</span><strong class="bad">{{ report.failed }}</strong></div>
          <div><span>异常</span><strong class="warn">{{ report.broken }}</strong></div>
          <div><span>跳过</span><strong>{{ report.skipped }}</strong></div>
          <div><span>通过率</span><strong>{{ passRate }}%</strong></div>
        </div>
        <el-empty v-else description="暂无执行结果" />
      </div>
    </div>

    <div class="panel">
      <h3>用例明细</h3>
      <el-table :data="report?.cases ?? []" height="420">
        <el-table-column prop="name" label="用例名称" min-width="260" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'passed' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'broken' ? 'warning' : 'info'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="120">
          <template #default="{ row }">{{ (row.duration_ms / 1000).toFixed(2) }} 秒</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.report-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
h3 { margin: 0 0 12px; font-size: 15px; }
.chart { height: 280px; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.stats div { padding: 14px; background: #f7f9fb; border-radius: 6px; }
.stats span { display: block; margin-bottom: 6px; color: #687385; font-size: 12px; }
.stats strong { font-size: 21px; }
.ok { color: #208154; }
.warn { color: #a36611; }
.bad { color: #c5342a; }
@media (max-width: 1000px) { .report-grid { grid-template-columns: 1fr; } }
</style>
