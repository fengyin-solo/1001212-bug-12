<template>
  <section class="page" data-module="door">
    <header class="page-head">
      <div>
        <h2>门到门配送管理</h2>
        <p class="page-desc">待配送、配送中、已签收三段分存；签收日期只落在对应任务编号上，已签收后不再允许改动。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记配送任务</button>
        <button class="btn" type="button" @click="openBatch">批量登记签收</button>
        <button class="btn" type="button" @click="exportRows">导出门到门配送清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>任务编号</span>
        <input v-model="keyword" placeholder="按任务编号检索" />
      </label>
      <label class="filter-item">
        <span>配送状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="stage in stages" :key="stage" :value="stage">{{ stage }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>
            <input
              type="checkbox"
              :checked="allDeliveringChecked"
              :disabled="!deliveringRows.length"
              title="全选本页配送中的任务"
              @change="toggleAllDelivering"
            />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>
            <input
              v-if="row.status === '配送中'"
              type="checkbox"
              :checked="checkedIds.includes(Number(row.id))"
              title="勾选后可批量登记签收"
              @change="toggleCheck(Number(row.id))"
            />
          </td>
          <td v-for="column in columns" :key="column">
            <span v-if="column === '配送状态'" class="stage-tag" :class="stageClass(row.status)">{{ row.status }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button v-if="row.status === '待配送'" class="link" type="button" @click="runStart(row)">开始配送</button>
            <button v-if="row.status === '配送中'" class="link" type="button" @click="openSign(row)">登记签收</button>
            <button v-if="row.status === '已签收'" class="link" type="button" @click="openSign(row)">签收信息</button>
            <button v-if="row.status !== '已签收'" class="link" type="button" @click="openEdit(row)">修正</button>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无门到门配送数据，可先登记配送任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条门到门配送记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记配送任务：失败时表单保留，可只重试这一条 -->
    <div v-if="createVisible" class="modal-mask">
      <div class="modal-panel">
        <header class="modal-head">
          <h3 class="modal-title">登记配送任务</h3>
          <button class="link" type="button" @click="createVisible = false">关闭</button>
        </header>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field" class="form-item">
            <span>{{ field }}{{ requiredOnCreate.includes(field) ? '（必填）' : '' }}</span>
            <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
          </label>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
            <button class="btn primary" type="submit">{{ createError ? '重试本条登记' : '提交登记' }}</button>
          </footer>
        </form>
      </div>
    </div>

    <!-- 详情：按 id 重新读取，进度与列表一致 -->
    <div v-if="detailVisible && detailRow" class="modal-mask">
      <div class="modal-panel">
        <header class="modal-head">
          <h3 class="modal-title">配送任务详情 · {{ detailRow['任务编号'] }}</h3>
          <button class="link" type="button" @click="detailVisible = false">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>
              <span v-if="field === '配送状态'" class="stage-tag" :class="stageClass(detailRow.status)">{{ detailRow.status }}</span>
              <template v-else>{{ detailRow[field] ?? '—' }}</template>
            </dd>
          </template>
        </dl>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="detailVisible = false">关闭</button>
        </footer>
      </div>
    </div>

    <!-- 签收弹窗：已签收的只读展示，不允许再改签收日期 -->
    <div v-if="signVisible && signRow" class="modal-mask">
      <div class="modal-panel">
        <header class="modal-head">
          <h3 class="modal-title">签收登记 · {{ signRow['任务编号'] }}</h3>
          <button class="link" type="button" @click="signVisible = false">关闭</button>
        </header>
        <p class="hint-text">
          当前进度：<span class="stage-tag" :class="stageClass(signRow.status)">{{ signRow.status }}</span>
        </p>
        <form class="modal-form" @submit.prevent="submitSign">
          <label class="form-item">
            <span>签收方式</span>
            <select v-model="signForm['签收方式']" :disabled="signReadonly">
              <option value="" disabled>请选择签收方式</option>
              <option v-for="method in signMethods" :key="method" :value="method">{{ method }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>签收日期</span>
            <input v-model="signForm['签收日期']" type="date" :disabled="signReadonly" />
          </label>
          <p v-if="signReadonly" class="hint-text">该任务已签收，签收日期不允许再改。</p>
          <p v-if="signError" class="error-text">{{ signError }}</p>
          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="signVisible = false">取消</button>
            <button v-if="!signReadonly" class="btn primary" type="submit">提交签收</button>
          </footer>
        </form>
      </div>
    </div>

    <!-- 修正（复核）：只改配送信息，签收日期不受影响 -->
    <div v-if="editVisible" class="modal-mask">
      <div class="modal-panel">
        <header class="modal-head">
          <h3 class="modal-title">修正配送任务</h3>
          <button class="link" type="button" @click="editVisible = false">关闭</button>
        </header>
        <form class="modal-form" @submit.prevent="submitEdit">
          <label v-for="field in editFields" :key="field" class="form-item">
            <span>{{ field }}</span>
            <input v-model="editForm[field]" :placeholder="`请输入${field}`" />
          </label>
          <p v-if="editError" class="error-text">{{ editError }}</p>
          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="editVisible = false">取消</button>
            <button class="btn primary" type="submit">保存修正</button>
          </footer>
        </form>
      </div>
    </div>

    <!-- 批量签收：被阻断的任务编号列出来，可只重试这些条目 -->
    <div v-if="batchVisible" class="modal-mask">
      <div class="modal-panel">
        <header class="modal-head">
          <h3 class="modal-title">批量登记签收</h3>
          <button class="link" type="button" @click="batchVisible = false">关闭</button>
        </header>
        <p class="hint-text">本次提交 {{ batchCodes.length }} 条：{{ batchCodes.join('、') }}</p>
        <form class="modal-form" @submit.prevent="submitBatch(false)">
          <label class="form-item">
            <span>签收方式</span>
            <select v-model="batchForm['签收方式']">
              <option value="" disabled>请选择签收方式</option>
              <option v-for="method in signMethods" :key="method" :value="method">{{ method }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>签收日期</span>
            <input v-model="batchForm['签收日期']" type="date" />
          </label>
          <div v-if="batchResult" class="batch-result">
            <p v-if="batchResult.signed.length" class="batch-ok">
              已签收 {{ batchResult.signed.length }} 条：{{ batchResult.signed.map((item) => item['任务编号']).join('、') }}
            </p>
            <div v-if="batchResult.blocked.length" class="batch-blocked">
              <p>被阻断 {{ batchResult.blocked.length }} 条：</p>
              <ul>
                <li v-for="item in batchResult.blocked" :key="item['任务编号']">
                  {{ item['任务编号'] }}：{{ item['原因'] }}
                </li>
              </ul>
            </div>
          </div>
          <p v-if="batchError" class="error-text">{{ batchError }}</p>
          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="batchVisible = false">关闭</button>
            <button
              v-if="batchResult && batchResult.blocked.length"
              class="btn primary"
              type="button"
              @click="submitBatch(true)"
            >
              仅重试被阻断的 {{ batchResult.blocked.length }} 条
            </button>
            <button v-else class="btn primary" type="submit">提交批量签收</button>
          </footer>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null | boolean>

interface BatchResult {
  signed: Array<Record<string, string>>
  blocked: Array<Record<string, string>>
}

const ENDPOINT = '/api/door'
const columns = ["任务编号", "关联调度", "配送站点", "配送地址", "配送人员", "计划时段", "签收方式", "签收日期", "配送状态"]
const stages = ["待配送", "配送中", "已签收"]
const signMethods = ["本人签收", "他人代收", "站点自提", "智能柜签收"]
const createFields = ["任务编号", "关联调度", "配送站点", "配送地址", "配送人员", "计划时段"]
const requiredOnCreate = ["任务编号", "关联调度", "配送站点"]
const editFields = ["关联调度", "配送站点", "配送地址", "配送人员", "计划时段"]
const detailFields = [...columns]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '待配送任务', value: 0 },
  { label: '配送中任务', value: 0 },
  { label: '已签收任务', value: 0 },
])
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const checkedIds = ref<number[]>([])

const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')

const detailVisible = ref(false)
const detailRow = ref<Row | null>(null)

const signVisible = ref(false)
const signRow = ref<Row | null>(null)
const signForm = ref<Record<string, string>>({ 签收方式: '', 签收日期: '' })
const signError = ref('')

const editVisible = ref(false)
const editId = ref<number | null>(null)
const editForm = ref<Record<string, string>>({})
const editError = ref('')

const batchVisible = ref(false)
const batchForm = ref<Record<string, string>>({ 签收方式: '', 签收日期: '' })
const batchCodes = ref<string[]>([])
const batchResult = ref<BatchResult | null>(null)
const batchError = ref('')

const today = new Date().toLocaleDateString('sv-SE')

const signReadonly = computed(() => signRow.value?.status === '已签收')
const deliveringRows = computed(() => rows.value.filter((row) => row.status === '配送中'))
const allDeliveringChecked = computed(
  () => deliveringRows.value.length > 0 && deliveringRows.value.every((row) => checkedIds.value.includes(Number(row.id))),
)

function stageClass(status: unknown) {
  if (status === '配送中') return 'doing'
  if (status === '已签收') return 'done'
  return 'pending'
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function toggleCheck(id: number) {
  checkedIds.value = checkedIds.value.includes(id)
    ? checkedIds.value.filter((item) => item !== id)
    : [...checkedIds.value, id]
}

function toggleAllDelivering() {
  const pageIds = deliveringRows.value.map((row) => Number(row.id))
  checkedIds.value = allDeliveringChecked.value
    ? checkedIds.value.filter((id) => !pageIds.includes(id))
    : [...new Set([...checkedIds.value, ...pageIds])]
}

// ---- 登记配送任务 ----
function openCreate() {
  createForm.value = {}
  createError.value = ''
  createVisible.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 表单数据保留在弹窗里，修正后点“重试本条登记”即可，不影响其他记录
      createError.value = payload.message ?? payload.detail ?? '配送任务登记未生效，请检查后重试'
      return
    }
    createVisible.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '配送任务登记失败'
  }
}

// ---- 详情 ----
async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('配送任务详情读取失败')
    }
    detailRow.value = await response.json()
    detailVisible.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '配送任务详情读取失败'
  }
}

// ---- 签收 ----
function openSign(row: Row) {
  signRow.value = row
  signError.value = ''
  signForm.value = row.status === '已签收'
    ? { 签收方式: String(row['签收方式'] ?? ''), 签收日期: String(row['签收日期'] ?? '') }
    : { 签收方式: '', 签收日期: today }
  signVisible.value = true
}

async function submitSign() {
  if (!signRow.value) return
  signError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${signRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '登记签收', ...signForm.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      signError.value = payload.message ?? '签收登记未生效，请检查后重试'
      return
    }
    signVisible.value = false
    await reload()
  } catch (error) {
    signError.value = error instanceof Error ? error.message : '签收登记失败'
  }
}

// ---- 修正（复核） ----
function openEdit(row: Row) {
  editId.value = Number(row.id)
  editForm.value = Object.fromEntries(editFields.map((field) => [field, String(row[field] ?? '')]))
  editError.value = ''
  editVisible.value = true
}

async function submitEdit() {
  if (editId.value === null) return
  editError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${editId.value}`, {
      method: 'PUT',
      body: JSON.stringify({ values: editForm.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      editError.value = payload.message ?? '修正保存未生效，请检查后重试'
      return
    }
    editVisible.value = false
    await reload()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '修正保存失败'
  }
}

// ---- 状态流转 ----
async function runStart(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '开始配送' } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message ?? '开始配送未生效，请稍后重试'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '门到门配送操作失败'
  }
}

// ---- 批量签收 ----
function openBatch() {
  const codes = deliveringRows.value
    .filter((row) => checkedIds.value.includes(Number(row.id)))
    .map((row) => String(row['任务编号']))
  if (!codes.length) {
    errorMessage.value = '请先在列表勾选配送中的任务，再批量登记签收'
    return
  }
  batchCodes.value = codes
  batchForm.value = { 签收方式: '', 签收日期: today }
  batchResult.value = null
  batchError.value = ''
  batchVisible.value = true
}

async function submitBatch(onlyBlocked: boolean) {
  batchError.value = ''
  const codes = onlyBlocked && batchResult.value
    ? batchResult.value.blocked.map((item) => item['任务编号'])
    : batchCodes.value
  const items = codes.map((code) => ({ 任务编号: code, ...batchForm.value }))
  try {
    const response = await request(`${ENDPOINT}/batch-signoff`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    })
    const payload = await response.json()
    if (!response.ok) {
      batchError.value = payload.detail ?? '批量签收提交失败，请稍后重试'
      return
    }
    batchResult.value = payload
    await reload()
    if (!payload.blocked?.length) {
      batchVisible.value = false
      checkedIds.value = []
    }
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '批量签收提交失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('配送任务列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      const summary = await summaryResponse.json()
      stats.value = [
        { label: '待配送任务', value: summary['待配送'] ?? 0 },
        { label: '配送中任务', value: summary['配送中'] ?? 0 },
        { label: '已签收任务', value: summary['已签收'] ?? 0 },
      ]
    }
    // 勾选状态只保留仍处在配送中的行，已签收的自动退出批量选择
    checkedIds.value = checkedIds.value.filter((id) =>
      rows.value.some((row) => Number(row.id) === id && row.status === '配送中'),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '门到门配送列表读取失败'
  }
}

onMounted(reload)
</script>
