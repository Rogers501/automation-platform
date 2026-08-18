import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getProjects, type Project } from '../api'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  async function loadProjects(force = false) {
    if (loaded.value && !force) return
    loading.value = true
    try {
      const { data } = await getProjects()
      projects.value = data
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  return { projects, loading, loaded, loadProjects }
})
