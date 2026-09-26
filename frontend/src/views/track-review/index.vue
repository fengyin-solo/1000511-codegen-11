<template>
  <section class="page" data-module="track-review">
    <header class="page-head">
      <div>
        <h2>分路不良复核测试概览</h2>
        <p class="page-desc">待复核区段按分路灵敏度与制式类型排列，复测结论与上次测试日一并登记；复核通过自动移出待办，同一区段重复复核只保留最新结论。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="reloadAll">刷新台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeGroup === tab.key }"
        type="button"
        @click="switchGroup(tab.key)"
      >
        {{ tab.label }}<span class="tab-badge">{{ tab.count }}</span>
      </button>
    </div>

    <form class="filter-bar" @submit.prevent="reloadRows(1)">
      <label class="filter-item">
        <span>设备编号 / 所属区段</span>
        <input v-model="keyword" placeholder="输入关键字检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetKeyword">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in activeColumns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td
            v-for="column in activeColumns"
            :key="column"
            :class="{ 'cell-invalid': errorsOf(row)[column] }"
          >
            {{ row[column] ?? '—' }}
            <span v-if="errorsOf(row)[column]" class="field-tip">{{ errorsOf(row)[column] }}</span>
          </td>
          <td class="row-actions">
            <button
              v-if="activeGroup === 'pending'"
              class="link"
              type="button"
              @click="openRecheck(row)"
            >提交复核</button>
            <button
              v-if="activeGroup === 'missing'"
              class="link"
              type="button"
              @click="openSupplement(row)"
            >补录灵敏度</button>
            <span v-if="activeGroup === 'ledger'" class="text-muted">台账存档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="activeColumns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条记录 · 第 {{ page }} 页</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="reloadRows(page - 1)">上一页</button>
        <button class="btn" type="button" :disabled="page * size >= total" @click="reloadRows(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 复核结论弹窗：校验不通过逐字段标红，可直接修正后重试 -->
    <div v-if="dialog.mode" class="modal-mask" @click.self="closeDialog">
      <div class="modal-card">
        <h3 class="modal-title">
          {{ dialog.mode === 'recheck' ? '提交复核结论' : '补录分路灵敏度' }}
        </h3>
        <p class="modal-sub">
          {{ dialog.row?.['设备编号'] }} · {{ dialog.row?.['制式类型'] }} ·
          {{ dialog.row?.['所属区段'] }}
          <template v-if="dialog.row?.['复测结论']">
            <br />上次结论：{{ dialog.row['复测结论'] }}（{{ dialog.row['复测日期'] }}，{{ dialog.row['复测人员'] }}）
          </template>
        </p>

        <template v-if="dialog.mode === 'recheck'">
          <label class="form-item">
            <span>复测结论 <em>*</em></span>
            <select v-model="form['复测结论']" :class="{ invalid: formErrors['复测结论'] }">
              <option value="">请选择复测结论</option>
              <option v-for="item in conclusions" :key="item" :value="item">{{ item }}</option>
            </select>
            <small v-if="formErrors['复测结论']" class="error-text">{{ formErrors['复测结论'] }}</small>
          </label>
          <label class="form-item">
            <span>复测日期 <em>*</em></span>
            <input v-model="form['复测日期']" type="date" :class="{ invalid: formErrors['复测日期'] }" />
            <small v-if="formErrors['复测日期']" class="error-text">{{ formErrors['复测日期'] }}</small>
          </label>
          <label class="form-item">
            <span>复测人员 <em>*</em></span>
            <input v-model="form['复测人员']" placeholder="填写复测人员" :class="{ invalid: formErrors['复测人员'] }" />
            <small v-if="formErrors['复测人员']" class="error-text">{{ formErrors['复测人员'] }}</small>
          </label>
        </template>

        <template v-else>
          <label class="form-item">
            <span>分路灵敏度 <em>*</em></span>
            <input v-model="form['分路灵敏度']" placeholder="例如 0.08Ω" :class="{ invalid: formErrors['分路灵敏度'] }" />
            <small v-if="formErrors['分路灵敏度']" class="error-text">{{ formErrors['分路灵敏度'] }}</small>
          </label>
        </template>

        <p v-if="dialogMessage" class="error-text">{{ dialogMessage }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitDialog">
            {{ submitting ? '提交中…' : '提交' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/track-reviews'
const PAGE_SIZE = 20

type GroupKey = 'pending' | 'missing' | 'ledger'
type Row = Record<string, string | number | null>
type FormValues = Record<string, string>

const sharedColumns = ["设备编号", "制式类型", "分路灵敏度", "所属区段", "上次测试日", "下次测试日", "设备状态", "复核状态"]
const ledgerColumns = ["设备编号", "制式类型", "分路灵敏度", "所属区段", "上次测试日", "复测日期", "复测结论", "复测人员", "复核状态"]

const tabs = [
  { key: 'pending' as GroupKey, label: '待复核', count: 0 },
  { key: 'missing' as GroupKey, label: '待补录', count: 0 },
  { key: 'ledger' as GroupKey, label: '复核台账', count: 0 },
]

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = PAGE_SIZE
const keyword = ref('')
const activeGroup = ref<GroupKey>('pending')
const errorMessage = ref('')
const conclusions = ref<string[]>(['复核通过', '复测仍不良'])
const fieldErrors = ref<Record<number, Record<string, string>>>({})

const statCards = ref([
  { label: '分路不良（复核前）', value: 0 },
  { label: '分路不良（复核后）', value: 0 },
  { label: '待复核', value: 0 },
  { label: '待补录', value: 0 },
  { label: '复核已通过', value: 0 },
])

const dialog = reactive<{ mode: '' | 'recheck' | 'supplement'; row: Row | null }>({
  mode: '',
  row: null,
})
const form = reactive<FormValues>({})
const formErrors = ref<Record<string, string>>({})
const dialogMessage = ref('')
const submitting = ref(false)

const activeColumns = computed(() => (activeGroup.value === 'ledger' ? ledgerColumns : sharedColumns))

function errorsOf(row: Row): Record<string, string> {
  if (row.id == null) return {}
  return fieldErrors.value[Number(row.id)] ?? {}
}
const emptyText = computed(() => {
  if (activeGroup.value === 'pending') return '暂无待复核区段，复核通过的区段已移出待办'
  if (activeGroup.value === 'missing') return '暂无待补录设备'
  return '台账暂无记录'
})

function resetKeyword() {
  keyword.value = ''
  void reloadRows(1)
}

function switchGroup(key: GroupKey) {
  activeGroup.value = key
  fieldErrors.value = {}
  void reloadRows(1)
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    statCards.value = statCards.value.map((card) => ({ ...card, value: payload[card.label] ?? card.value }))
    const pendingTab = tabs.find((item) => item.key === 'pending')
    const missingTab = tabs.find((item) => item.key === 'missing')
    const ledgerTab = tabs.find((item) => item.key === 'ledger')
    if (pendingTab) pendingTab.count = payload['待复核'] ?? 0
    if (missingTab) missingTab.count = payload['待补录'] ?? 0
  } catch {
    // 统计读不出来时保留上一次数值，列表错误在页脚提示
  }
}

async function loadLedgerCount() {
  try {
    const response = await request(`${ENDPOINT}?group=ledger&page=1&size=1`)
    if (response.ok) {
      const payload = await response.json()
      const ledgerTab = tabs.find((item) => item.key === 'ledger')
      if (ledgerTab) ledgerTab.count = payload.total ?? 0
    }
  } catch {
    // 徽标读不出来不阻断主流程
  }
}

async function reloadRows(targetPage = page.value) {
  errorMessage.value = ''
  page.value = targetPage
  const query = new URLSearchParams({
    group: activeGroup.value,
    page: String(targetPage),
    size: String(PAGE_SIZE),
  })
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('复核台账读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复核台账读取失败'
  }
}

async function reloadAll() {
  await Promise.all([loadStats(), loadLedgerCount(), reloadRows()])
}

function todayText() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function openRecheck(row: Row) {
  dialog.mode = 'recheck'
  dialog.row = row
  form['复测结论'] = ''
  form['复测日期'] = todayText()
  form['复测人员'] = ''
  formErrors.value = {}
  dialogMessage.value = ''
}

function openSupplement(row: Row) {
  dialog.mode = 'supplement'
  dialog.row = row
  form['分路灵敏度'] = ''
  formErrors.value = {}
  dialogMessage.value = ''
}

function closeDialog() {
  if (submitting.value) return
  dialog.mode = ''
  dialog.row = null
  dialogMessage.value = ''
  formErrors.value = {}
}

async function submitDialog() {
  if (!dialog.row || !dialog.mode) return
  submitting.value = true
  dialogMessage.value = ''
  formErrors.value = {}
  const action = dialog.mode === 'recheck' ? 'recheck' : 'supplement'
  try {
    const response = await request(`${ENDPOINT}/${dialog.row.id}/${action}`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      // 校验不通过：字段错误标到弹窗与对应行，允许直接改完重试
      const errors = payload?.entry?.errors ?? {}
      formErrors.value = errors
      if (dialog.row.id != null) {
        fieldErrors.value[Number(dialog.row.id)] = errors
      }
      dialogMessage.value = payload?.message ?? '提交未通过校验，请修正后重试'
      return
    }
    const rowId = Number(dialog.row.id)
    delete fieldErrors.value[rowId]
    closeDialog()
    await reloadAll()
  } catch (error) {
    dialogMessage.value = error instanceof Error ? error.message : '提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  void reloadAll()
})
</script>
