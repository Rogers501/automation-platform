<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { getCases, type TestCase } from '../api'
import { useProjectStore } from '../stores/project'

const store = useProjectStore()
const state = reactive({ project: '', env: '' })
const cases = ref<TestCase[]>([])
const keyword = ref('')
const loading = ref(false)

const filtered = ref<TestCase[]>([])

async function loadCases() {
  if (!state.project || !state.env) return
  loading.value = true
  try {
    const { data } = await getCases(state.project, state.env)
    cases.value = data.cases
    filterCases()
  } finally {
    loading.value = false
  }
}

function filterCases() {
  const word = keyword.value.trim().toLowerCase()
  filtered.value = word
    ? cases.value.filter((item) =>
        [item.name, item.description, item.file, ...item.tags].join(' ').toLowerCase().includes(word),
      )
    : cases.value
}

onMounted(async () => {
  await store.loadProjects()
  const first = store.projects[0]
  if (first) {
    state.project = first.name
    state.env = first.envs[0] ?? 'test'
  }
})

watch(() => [state.project, state.env], loadCases)
</script>

<template>
  <div>
    <div class="panel toolbar">
      <el-select v-model="state.project" filterable placeholder="选择项目" style="width: 180px">
        <el-option v-for="item in store.projects" :key="item.name" :label="item.name" :value="item.name" />
      </el-select>
      <el-select v-model="state.env" placeholder="选择环境" style="width: 130px">
        <el-option v-for="item in store.projects.find(p => p.name === state.project)?.envs ?? ['test']" :key="item" :label="item" :value="item" />
      </el-select>
      <el-input v-model="keyword" clearable placeholder="搜索用例名、描述、文件或标签" style="width: 320px" @input="filterCases" />
      <span class="muted">共 {{ filtered.length }} 条用例</span>
    </div>

    <div class="panel">
      <el-table v-loading="loading" :data="filtered" height="640" row-key="id">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="case-detail">
              <p><b>用例 ID：</b><span class="mono">{{ row.id }}</span></p>
              <p><b>用例描述：</b>{{ row.description || '未填写' }}</p>
              <p><b>数据驱动：</b>{{ row.data_driven ? `是，${row.data_cases.length} 组数据` : '否' }}</p>
              <el-alert v-if="row.data_driven" type="info" :closable="false">
                <pre class="data-json">{{ JSON.stringify(row.data_cases, null, 2) }}</pre>
              </el-alert>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="用例名称" min-width="180" />
        <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
        <el-table-column label="标签" min-width="130">
          <template #default="{ row }">
            <el-tag v-for="tag in row.tags" :key="tag" size="small" class="tag">{{ tag }}</el-tag>
            <span v-if="row.tags.length === 0" class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column prop="file" label="所属文件" min-width="180" />
        <el-table-column label="数据驱动" width="100">
          <template #default="{ row }">
            <el-tag :type="row.data_driven ? 'success' : 'info'" effect="plain">{{ row.data_driven ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.tag { margin-right: 4px; }
.case-detail { padding: 4px 12px; }
.case-detail p { margin: 6px 0; }
.data-json { max-height: 280px; margin: 0; overflow: auto; font-size: 12px; white-space: pre-wrap; }
</style>
