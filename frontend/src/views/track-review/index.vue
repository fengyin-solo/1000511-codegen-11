<template>
  <section class="page" data-module="track-review">
    <header class="page-head">
      <div>
        <h2>分路不良复核测试概览</h2>
        <p class="page-desc">待复核区段按分路灵敏度与制式类型排列，复测结论与上次测试日直接入账；相邻区段以前是否分路不良一并列在提示里，不用再翻记录。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/track">返回轨道电路列表</RouterLink>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="scope-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="btn"
        :class="{ primary: scope === tab.key }"
        type="button"
        @click="switchScope(tab.key)"
      >
        {{ tab.label }}<span class="tab-count">{{ tabCounts[tab.key] }}</span>
      </button>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>设备编号/所属区段</span>
        <input v-model.trim="keyword" placeholder="按设备编号或区段检索" />
      </label>
      <label class="filter-item">
        <span>制式类型</span>
        <input v-model.trim="systemFilter" placeholder="如 25Hz、ZPW-2000" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column.key">
            <span v-if="column.key === '复测结论' && row[column.key]" :class="['result-tag', row[column.key] === '通过' ? 'pass' : 'fail']">
              {{ row[column.key] }}
            </span>
            <span v-else>{{ formatCell(row[column.key]) }}</span>
          </td>
          <td class="row-actions">
            <template v-if="scope === 'pending'">
              <button class="link" type="button" @click="openReview(row)">复核登记</button>
            </template>
            <template v-else-if="scope === 'backfill'">
              <button class="link" type="button" @click="openBackfill(row)">补录灵敏度</button>
            </template>
            <template v-else>
              <button
                v-if="row.status === '分路不良'"
                class="link"
                type="button"
                @click="openReview(row)"
              >
                再次复核
              </button>
              <span v-else class="muted-text">已闭环</span>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ scopeLabel }}记录</span>
      <span v-if="notice" class="notice-text">{{ notice }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 复核登记弹层：校验不过的字段标红，改完直接重试 -->
    <div v-if="reviewTarget" class="modal-mask" @click.self="closeForms">
      <div class="modal-card">
        <h3>复核登记 · {{ reviewTarget.设备编号 }}（{{ reviewTarget.所属区段 }}）</h3>
        <p class="modal-hint">残压限值 {{ reviewTarget.残压限值 }}V；实测分路残压超过限值时不能判为通过。</p>
        <form @submit.prevent="submitReview">
          <label class="form-row" :class="{ invalid: formErrors.复测结论 }">
            <span>复测结论</span>
            <select v-model="reviewForm.复测结论">
              <option value="" disabled>请选择复测结论</option>
              <option value="通过">通过</option>
              <option value="不通过">不通过</option>
            </select>
            <em v-if="formErrors.复测结论">{{ formErrors.复测结论 }}</em>
          </label>
          <label class="form-row" :class="{ invalid: formErrors.分路残压 }">
            <span>分路残压(V)</span>
            <input v-model.trim="reviewForm.分路残压" placeholder="通过时必填，单位 V" />
            <em v-if="formErrors.分路残压">{{ formErrors.分路残压 }}</em>
          </label>
          <label class="form-row" :class="{ invalid: formErrors.复核测试日 }">
            <span>复核测试日</span>
            <input v-model.trim="reviewForm.复核测试日" placeholder="YYYY-MM-DD" />
            <em v-if="formErrors.复核测试日">{{ formErrors.复核测试日 }}</em>
          </label>
          <label class="form-row" :class="{ invalid: formErrors.复核人 }">
            <span>复核人</span>
            <input v-model.trim="reviewForm.复核人" placeholder="值班复核人员" />
            <em v-if="formErrors.复核人">{{ formErrors.复核人 }}</em>
          </label>
          <div class="modal-actions">
            <button class="btn" type="button" @click="closeForms">取消</button>
            <button class="btn primary" type="submit">提交复核</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 待补录：补录分路灵敏度 -->
    <div v-if="backfillTarget" class="modal-mask" @click.self="closeForms">
      <div class="modal-card">
        <h3>补录分路灵敏度 · {{ backfillTarget.设备编号 }}</h3>
        <form @submit.prevent="submitBackfill">
          <label class="form-row" :class="{ invalid: backfillErrors.分路灵敏度 }">
            <span>分路灵敏度(Ω)</span>
            <input v-model.trim="backfillForm.分路灵敏度" placeholder="如 0.15，单位 Ω" />
            <em v-if="backfillErrors.分路灵敏度">{{ backfillErrors.分路灵敏度 }}</em>
          </label>
          <div class="modal-actions">
            <button class="btn" type="button" @click="closeForms">取消</button>
            <button class="btn primary" type="submit">保存并进入待复核</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stats = Record<string, number>

const ENDPOINT = '/api/track/review'

const tabs = [
  { key: 'pending', label: '待复核' },
  { key: 'backfill', label: '待补录' },
  { key: 'ledger', label: '复核台账' },
] as const

type ScopeKey = (typeof tabs)[number]['key']
const tabCounts = reactive<Record<ScopeKey, number>>({ pending: 0, backfill: 0, ledger: 0 })

const pendingColumns = [
  { key: '设备编号', label: '设备编号' },
  { key: '所属区段', label: '所属区段' },
  { key: '制式类型', label: '制式类型' },
  { key: '分路灵敏度', label: '分路灵敏度(Ω)' },
  { key: '上次测试日', label: '上次测试日' },
  { key: '复测结论', label: '上次复核结论' },
  { key: '相邻区段提示', label: '相邻区段情况' },
]
const backfillColumns = [
  { key: '设备编号', label: '设备编号' },
  { key: '所属区段', label: '所属区段' },
  { key: '制式类型', label: '制式类型' },
  { key: '区段长度', label: '区段长度' },
  { key: '上次测试日', label: '上次测试日' },
  { key: '相邻区段提示', label: '相邻区段情况' },
]
const ledgerColumns = [
  { key: '设备编号', label: '设备编号' },
  { key: '所属区段', label: '所属区段' },
  { key: '制式类型', label: '制式类型' },
  { key: '分路灵敏度', label: '分路灵敏度(Ω)' },
  { key: '上次测试日', label: '上次测试日' },
  { key: '复测结论', label: '复测结论' },
  { key: '复核测试日', label: '复核测试日' },
  { key: '相邻区段提示', label: '相邻区段情况' },
  { key: 'status', label: '当前状态' },
]

const scope = ref<ScopeKey>('pending')
const rows = ref<Row[]>([])
const total = ref(0)
const scopeLabel = ref('待复核')
const stats = ref<Stats>({})
const keyword = ref('')
const systemFilter = ref('')
const errorMessage = ref('')
const notice = ref('')

const columns = computed(() => {
  if (scope.value === 'backfill') return backfillColumns
  if (scope.value === 'ledger') return ledgerColumns
  return pendingColumns
})

const emptyText = computed(() => {
  if (scope.value === 'pending') return '没有待复核区段，分路不良均已闭环'
  if (scope.value === 'backfill') return '没有待补录分路灵敏度的设备'
  return '台账暂无复核记录'
})

const statCards = computed(() => [
  { label: '分路不良区段', value: stats.value['分路不良区段'] ?? 0 },
  { label: '待复核', value: stats.value['待复核'] ?? 0 },
  { label: '待补录', value: stats.value['待补录'] ?? 0 },
  { label: '累计复核通过', value: stats.value['累计复核通过'] ?? 0 },
])

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function switchScope(next: ScopeKey) {
  scope.value = next
  reload()
}

function resetFilters() {
  keyword.value = ''
  systemFilter.value = ''
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams({ scope: scope.value })
  if (keyword.value) query.set('keyword', keyword.value)
  if (systemFilter.value) query.set('system', systemFilter.value)
  try {
    const response = await request(`${ENDPOINT}/overview?${query.toString()}`)
    if (!response.ok) throw new Error('复核概览读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    scopeLabel.value = payload.scopeLabel ?? ''
    stats.value = payload.stats ?? {}
    tabCounts.pending = stats.value['待复核'] ?? 0
    tabCounts.backfill = stats.value['待补录'] ?? 0
    tabCounts.ledger = total.value
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复核概览读取失败'
  }
}

// ---- 复核登记 ----
const reviewTarget = ref<Row | null>(null)
const reviewForm = reactive({ 复测结论: '不通过', 分路残压: '', 复核测试日: today(), 复核人: '' })
const formErrors = reactive<Record<string, string>>({})

function today() {
  return new Date().toISOString().slice(0, 10)
}

function openReview(row: Row) {
  reviewTarget.value = row
  reviewForm.复测结论 = '不通过'
  reviewForm.分路残压 = ''
  reviewForm.复核测试日 = today()
  reviewForm.复核人 = ''
  Object.keys(formErrors).forEach((key) => delete formErrors[key])
}

async function submitReview() {
  if (!reviewTarget.value) return
  errorMessage.value = ''
  Object.keys(formErrors).forEach((key) => delete formErrors[key])
  try {
    const response = await request(`${ENDPOINT}/${reviewTarget.value.id}/submit`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...reviewForm } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      if (payload.errors) Object.assign(formErrors, payload.errors)
      errorMessage.value = payload.message || '复核校验未通过'
      return
    }
    const { before, after } = payload.stats ?? {}
    if (before && after) {
      notice.value = `${payload.message}；分路不良 ${before['分路不良区段']} → ${after['分路不良区段']}，待复核 ${before['待复核']} → ${after['待复核']}`
      setTimeout(() => (notice.value = ''), 6000)
    }
    closeForms()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复核提交失败，可修正后重试'
  }
}

// ---- 补录灵敏度 ----
const backfillTarget = ref<Row | null>(null)
const backfillForm = reactive({ 分路灵敏度: '' })
const backfillErrors = reactive<Record<string, string>>({})

function openBackfill(row: Row) {
  backfillTarget.value = row
  backfillForm.分路灵敏度 = ''
  Object.keys(backfillErrors).forEach((key) => delete backfillErrors[key])
}

async function submitBackfill() {
  if (!backfillTarget.value) return
  errorMessage.value = ''
  Object.keys(backfillErrors).forEach((key) => delete backfillErrors[key])
  try {
    const response = await request(`${ENDPOINT}/${backfillTarget.value.id}/backfill`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...backfillForm } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      if (payload.errors) Object.assign(backfillErrors, payload.errors)
      errorMessage.value = payload.message || '补录校验未通过'
      return
    }
    notice.value = payload.message
    setTimeout(() => (notice.value = ''), 6000)
    closeForms()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '补录失败，可重试'
  }
}

function closeForms() {
  reviewTarget.value = null
  backfillTarget.value = null
}

onMounted(reload)
</script>

<style scoped>
.scope-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.tab-count {
  margin-left: 6px;
  font-size: 12px;
  opacity: 0.8;
}
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
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.notice-text {
  color: #117a37;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 460px;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-card h3 {
  margin: 0 0 6px;
  font-size: 15px;
}
.modal-hint {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 12px;
}
.form-row {
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: center;
  gap: 4px 10px;
  margin-bottom: 10px;
  font-size: 13px;
}
.form-row span {
  color: var(--muted);
}
.form-row input,
.form-row select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.form-row em {
  grid-column: 2;
  color: #b42318;
  font-size: 12px;
  font-style: normal;
}
.form-row.invalid input,
.form-row.invalid select {
  border-color: #b42318;
  background: #fef3f2;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>
