import axios from 'axios'

export const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export interface Project {
  name: string
  description: string
  envs: string[]
  case_count: number
  test_files?: TestFile[]
}

export interface TestFile {
  path: string
  name: string
  module: string
}

export interface TestCase {
  id: string
  file: string
  name: string
  description: string
  tags: string[]
  data_driven: boolean
  data_cases: Array<{ file: string; case: Record<string, unknown> }>
}

export interface ReportCase {
  name: string
  status: string
  duration_ms: number
  start: number
  labels: string[]
}

export interface Report {
  project: string
  total: number
  passed: number
  failed: number
  broken: number
  skipped: number
  cases: ReportCase[]
  message?: string
}

export interface ExecutionRecord {
  id: string
  project: string
  env: string
  test_paths: string[]
  status: string
  started_at: string
  finished_at?: string
}

export const getProjects = () => http.get<Project[]>('/projects')
export const getCases = (project: string, env: string) =>
  http.get<{ project: string; env: string; total: number; cases: TestCase[] }>(
    `/projects/${project}/cases`,
    { params: { env } },
  )
export const getReport = (project: string) => http.get<Report>(`/projects/${project}/report`)
export const getExecutions = () => http.get<ExecutionRecord[]>('/executions')
export const startExecution = (data: { project: string; env: string; test_paths: string[] }) =>
  http.post<{ execution_id: string; status: string }>('/executions', data)
