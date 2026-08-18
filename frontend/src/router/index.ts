import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/Dashboard.vue'),
      meta: { title: '首页', description: '查看项目概览、最近执行和整体质量情况' },
    },
    {
      path: '/cases',
      name: 'cases',
      component: () => import('../views/TestCases.vue'),
      meta: { title: '用例查询', description: '按项目和环境查询可执行的自动化用例' },
    },
    {
      path: '/executions',
      name: 'executions',
      component: () => import('../views/Execution.vue'),
      meta: { title: '测试执行', description: '选择项目、环境和用例后启动测试' },
    },
    {
      path: '/reports',
      name: 'reports',
      component: () => import('../views/Reports.vue'),
      meta: { title: '报告中心', description: '查看 Allure 结果统计和失败用例明细' },
    },
  ],
})

export default router
