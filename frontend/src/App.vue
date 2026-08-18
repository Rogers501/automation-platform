<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="220px" class="app-aside">
      <div class="brand">
        <span class="brand-mark">AP</span>
        <span>自动化测试平台</span>
      </div>
      <el-menu router :default-active="route.path" class="aside-menu">
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/cases">
          <el-icon><Search /></el-icon>
          <span>用例查询</span>
        </el-menu-item>
        <el-menu-item index="/executions">
          <el-icon><VideoPlay /></el-icon>
          <span>测试执行</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DataAnalysis /></el-icon>
          <span>报告中心</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div>
          <p class="page-title">{{ route.meta.title }}</p>
          <p class="page-subtitle">{{ route.meta.description }}</p>
        </div>
        <el-tag effect="plain">本地工作台</el-tag>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
