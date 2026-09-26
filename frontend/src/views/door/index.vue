<template>
  <section class="page" data-module="door">
    <header class="page-head">
      <div>
        <h2>门到门配送管理</h2>
        <p class="page-desc">待配送、配送中、已签收三段分开存放；签收日期只落在对应任务编号上，已签收后不可再改。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记配送任务</button>
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
        <input v-model="filters.keyword" placeholder="按任务编号检索" />
      </label>
      <label class="filter-item">
        <span>配送进度</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
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
            <span v-if="column === '配送状态'" class="stage-tag" :data-stage="row[column]">
              {{ row[column] || '—' }}
            </span>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-if="row['配送状态'] === '待配送'"
              class="link"
              type="button"
              @click="startDelivery(row)"
            >开始配送</button>
            <button
              v-if="row['配送状态'] === '配送中'"
              class="link"
              type="button"
              @click="openSign(row)"
            >签收登记</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无门到门配送数据，可先登记配送任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条门到门配送记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 详情页：与列表、签收弹窗共用同一份后端数据，进度口径一致 -->
    <div v-if="detailRow" class="dialog-mask" @click.self="closeDetail">
      <div class="dialog">
        <header class="dialog-head">
          <h3>配送任务详情 · {{ detailRow['任务编号'] }}</h3>
          <span class="stage-tag" :data-stage="detailRow['配送状态']">{{ detailRow['配送状态'] }}</span>
        </header>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detailRow[field] || '—' }}</dd>
          </template>
        </dl>
        <p v-if="detailRow['配送状态'] === '已签收'" class="dialog-note">
          该任务已签收，签收日期不允许再修改。
        </p>
        <footer class="dialog-foot">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </footer>
      </div>
    </div>

    <!-- 签收弹窗：签收方式 + 签收日期只写入当前任务编号 -->
    <div v-if="signRow" class="dialog-mask" @click.self="closeSign">
      <div class="dialog">
        <header class="dialog-head">
          <h3>签收登记 · {{ signRow['任务编号'] }}</h3>
          <span class="stage-tag" :data-stage="signRow['配送状态']">{{ signRow['配送状态'] }}</span>
        </header>
        <div class="form-grid">
          <label class="form-item">
            <span>签收方式</span>
            <select v-model="signForm['签收方式']">
              <option value="" disabled>请选择签收方式</option>
              <option v-for="way in signWays" :key="way" :value="way">{{ way }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>签收日期</span>
            <input v-model="signForm['签收日期']" type="date" />
          </label>
        </div>
        <p v-if="signError" class="error-text">{{ signError }}</p>
        <footer class="dialog-foot">
          <button class="btn ghost" type="button" @click="closeSign">取消</button>
          <button class="btn primary" type="button" :disabled="signSubmitting" @click="submitSign">
            {{ signSubmitting ? '提交中…' : '确认签收' }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 登记 / 补录：批量提交，被阻断的行留在列表里，可只重试这一条 -->
    <div v-if="createVisible" class="dialog-mask" @click.self="closeCreate">
      <div class="dialog wide">
        <header class="dialog-head">
          <h3>登记配送任务</h3>
          <button class="link" type="button" @click="addDraft">添加一行</button>
        </header>
        <table class="data-table">
          <thead>
            <tr>
              <th v-for="field in draftFields" :key="field">
                {{ field }}<span v-if="requiredDraftFields.includes(field)" class="required-mark">*</span>
              </th>
              <th>提交结果</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(draft, index) in drafts" :key="draft.uid">
              <td v-for="field in draftFields" :key="field">
                <input v-model="draft.values[field]" :placeholder="field" />
              </td>
              <td>
                <span v-if="draft.error" class="error-text">{{ draft.error }}</span>
                <span v-else class="muted">待提交</span>
              </td>
              <td class="row-actions">
                <button
                  v-if="draft.error"
                  class="link"
                  type="button"
                  :disabled="draft.submitting"
                  @click="retryDraft(index)"
                >{{ draft.submitting ? '重试中…' : '重试' }}</button>
                <button class="link" type="button" @click="removeDraft(index)">移除</button>
              </td>
            </tr>
            <tr v-if="!drafts.length">
              <td :colspan="draftFields.length + 2" class="empty-state">点击「添加一行」补录配送任务</td>
            </tr>
          </tbody>
        </table>
        <p v-if="createMessage" class="error-text">{{ createMessage }}</p>
        <footer class="dialog-foot">
          <button class="btn ghost" type="button" @click="closeCreate">关闭</button>
          <button
            class="btn primary"
            type="button"
            :disabled="createSubmitting || !drafts.length"
            @click="submitDrafts()"
          >{{ createSubmitting ? '提交中…' : '提交登记' }}</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Draft = { uid: number; values: Record<string, string>; error: string; submitting: boolean }

const ENDPOINT = '/api/door'
const columns = ["任务编号", "关联调度", "配送站点", "配送地址", "配送人员", "计划时段", "签收方式", "签收日期", "配送状态"]
const detailFields = columns
const statuses = ["待配送", "配送中", "已签收"]
const signWays = ["本人签收", "他人代收", "站点代收", "快递柜投放"]
const draftFields = ["任务编号", "关联调度", "配送站点", "配送地址", "配送人员", "计划时段"]
const requiredDraftFields = ["任务编号", "关联调度", "配送站点"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref({ keyword: '', status: '' })
const stats = ref(statuses.map((status) => ({ label: `${status}任务`, value: 0 })))

const detailRow = ref<Row | null>(null)

const signRow = ref<Row | null>(null)
const signForm = reactive<Record<string, string>>({ 签收方式: '', 签收日期: '' })
const signError = ref('')
const signSubmitting = ref(false)

const createVisible = ref(false)
const drafts = ref<Draft[]>([])
const createMessage = ref('')
const createSubmitting = ref(false)
let draftUid = 0

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function loadSummary() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) return
    const payload = await response.json()
    stats.value = statuses.map((status) => ({ label: `${status}任务`, value: payload[status] ?? 0 }))
  } catch {
    // 统计读取失败不阻塞列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('配送任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '门到门配送列表读取失败'
  }
}

async function refresh() {
  await Promise.all([reload(), loadSummary()])
  if (detailRow.value) {
    const response = await request(`${ENDPOINT}/${detailRow.value.id}`)
    if (response.ok) {
      detailRow.value = await response.json()
    }
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('配送任务详情读取失败')
    }
    detailRow.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '配送任务详情读取失败'
  }
}

function closeDetail() {
  detailRow.value = null
}

async function startDelivery(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action: '开始配送' }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '开始配送未生效，请稍后重试')
    }
    await refresh()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '门到门配送操作失败'
  }
}

async function openSign(row: Row) {
  signError.value = ''
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('配送任务读取失败')
    }
    const fresh = await response.json()
    if (fresh['配送状态'] !== '配送中') {
      errorMessage.value = `任务 ${fresh['任务编号']} 当前为「${fresh['配送状态']}」，不能登记签收`
      await refresh()
      return
    }
    signRow.value = fresh
    signForm['签收方式'] = ''
    signForm['签收日期'] = new Date().toISOString().slice(0, 10)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '配送任务读取失败'
  }
}

function closeSign() {
  signRow.value = null
  signError.value = ''
}

async function submitSign() {
  if (!signRow.value) return
  signError.value = ''
  signSubmitting.value = true
  try {
    const response = await request(`${ENDPOINT}/${signRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        action: '完成签收',
        任务编号: signRow.value['任务编号'],
        签收方式: signForm['签收方式'],
        签收日期: signForm['签收日期'],
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      signError.value = payload.message ?? payload.detail ?? '签收登记未生效，请稍后重试'
      return
    }
    signRow.value = null
    await refresh()
  } catch (error) {
    signError.value = error instanceof Error ? error.message : '签收登记失败'
  } finally {
    signSubmitting.value = false
  }
}

function openCreate() {
  createMessage.value = ''
  createVisible.value = true
  if (!drafts.value.length) {
    addDraft()
  }
}

function closeCreate() {
  createVisible.value = false
}

function addDraft() {
  draftUid += 1
  const values: Record<string, string> = {}
  for (const field of draftFields) values[field] = ''
  drafts.value.push({ uid: draftUid, values, error: '', submitting: false })
}

function removeDraft(index: number) {
  drafts.value.splice(index, 1)
}

function retryDraft(index: number) {
  drafts.value[index].error = ''
  void submitDrafts([index])
}

async function submitDrafts(indices?: number[]) {
  const targets = indices ?? drafts.value.map((_, index) => index)
  if (!targets.length) return
  createMessage.value = ''
  createSubmitting.value = true
  for (const index of targets) drafts.value[index].submitting = true
  try {
    const response = await request(`${ENDPOINT}/batch`, {
      method: 'POST',
      body: JSON.stringify({ rows: targets.map((index) => drafts.value[index].values) }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail ?? '配送任务登记请求未生效')
    }
    const blockedAt = new Set<number>()
    for (const item of payload.blocked ?? []) {
      const draftIndex = targets[item.index]
      if (draftIndex !== undefined && drafts.value[draftIndex]) {
        drafts.value[draftIndex].error = item.reason
        blockedAt.add(draftIndex)
      }
    }
    // 已登记的行从草稿里移除（倒序删除，避免下标位移），失败的留在原处等待重试
    const succeeded = targets.filter((index) => !blockedAt.has(index)).sort((a, b) => b - a)
    for (const index of succeeded) drafts.value.splice(index, 1)
    createMessage.value = payload.ok ? '' : payload.message
    if (!drafts.value.length) {
      createVisible.value = false
    }
    await refresh()
  } catch (error) {
    createMessage.value = error instanceof Error ? error.message : '配送任务登记失败'
  } finally {
    createSubmitting.value = false
    for (const draft of drafts.value) draft.submitting = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.dialog {
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  width: 560px;
  max-width: calc(100vw - 40px);
  max-height: calc(100vh - 60px);
  overflow: auto;
}
.dialog.wide { width: 900px; }
.dialog-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.dialog-head h3 { margin: 0; font-size: 15px; }
.dialog-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.dialog-note { color: var(--muted); font-size: 12px; }
.detail-grid {
  display: grid;
  grid-template-columns: 84px 1fr 84px 1fr;
  gap: 8px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input,
.form-item select,
.filter-item select,
td input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  background: #fff;
}
.stage-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #eef2f7;
}
.stage-tag[data-stage='待配送'] { background: #fff7e6; color: #ad6800; }
.stage-tag[data-stage='配送中'] { background: #e6f4ff; color: #0958d9; }
.stage-tag[data-stage='已签收'] { background: #f6ffed; color: #389e0d; }
.required-mark { color: #b42318; margin-left: 2px; }
.muted { color: var(--muted); font-size: 12px; }
</style>
