<template>
  <section class="page" data-module="track">
    <header class="page-head">
      <div>
        <h2>轨道电路管理</h2>
        <p class="page-desc">维护轨道电路，围绕设备编号、制式类型、区段长度、分路灵敏度做登记、筛选与状态流转；复测结论与复核测试日和复核台账同源。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn primary" to="/track-review">分路不良复核概览</RouterLink>
        <button class="btn" type="button" @click="openCreate">登记轨道电路</button>
        <button class="btn" type="button" @click="exportRows">导出轨道电路清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '复测结论' && row[column]" :class="['result-tag', row[column] === '通过' ? 'pass' : 'fail']">{{ row[column] }}</span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <RouterLink v-if="row.status === '分路不良'" class="link" to="/track-review">去复核</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无轨道电路数据，可先登记轨道电路</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条轨道电路记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type TrackStats = Record<string, number>

const ENDPOINT = '/api/track'
const columns = ["设备编号", "制式类型", "区段长度", "分路灵敏度", "残压限值", "所属区段", "上次测试日", "下次测试日", "复测结论", "复核测试日", "设备状态"]
const actions = ["提交测试", "确认正常", "更换设备"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = ["设备编号", "制式类型", "所属区段"]
const stats = ref<TrackStats>({})

const statCards = computed(() => [
  { label: '在运轨道电路', value: stats.value['在运轨道电路'] ?? 0 },
  { label: '分路不良区段', value: stats.value['分路不良区段'] ?? 0 },
  { label: '待复核', value: stats.value['待复核'] ?? 0 },
  { label: '待补录', value: stats.value['待补录'] ?? 0 },
  { label: '待测试设备', value: stats.value['待测试设备'] ?? 0 },
])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '轨道电路登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '轨道电路动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '轨道电路操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      stats.value = await response.json()
    }
  } catch {
    // 统计卡片读不到时保留上一次数据，不打断列表操作
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('轨道电路列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '轨道电路列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.result-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.result-tag.pass {
  background: #e7f6ec;
  color: #117a37;
}
.result-tag.fail {
  background: #fdecec;
  color: #b42318;
}
</style>
