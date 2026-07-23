<template>
  <div>
    <NavBar />

    <!-- 双列布局：左边栏 + 右侧聊天区 -->
    <div style="display:flex;height:calc(100vh - 60px);background:#f5f7fa;overflow:hidden">

      <!-- 左侧边栏 -->
      <div style="width:220px;min-width:180px;border-right:1px solid #e5e7eb;
                  background:#fff;display:flex;flex-direction:column;overflow:hidden;flex-shrink:0">
        <!-- 新建对话 -->
        <div style="padding:12px;border-bottom:1px solid #f3f4f6">
          <button
            @click="createSession"
            style="width:100%;padding:8px 0;background:#4f46e5;color:#fff;border:none;
                   border-radius:8px;font-size:13px;cursor:pointer"
          >+ 新建对话</button>
        </div>

        <!-- 会话列表 -->
        <div style="flex:1;overflow-y:auto;padding:6px 6px 12px">
          <div
            v-for="s in sessions" :key="s.session_id"
            style="position:relative;margin-bottom:2px"
          >
            <div
              style="display:flex;align-items:center;border-radius:6px;transition:background 0.1s"
              :style="s.session_id === sessionId
                ? 'background:#eef2ff'
                : 'background:transparent'"
              @mouseenter="e => { if(s.session_id !== sessionId) e.currentTarget.style.background='#f9fafb' }"
              @mouseleave="e => { if(s.session_id !== sessionId) e.currentTarget.style.background='transparent' }"
            >
              <!-- 会话名 -->
              <button
                @click="switchSession(s.session_id)"
                style="flex:1;text-align:left;background:transparent;border:none;
                       padding:8px 6px 8px 10px;font-size:13px;cursor:pointer;
                       overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:0"
                :style="s.session_id === sessionId ? 'color:#4f46e5;font-weight:500' : 'color:#374151'"
              >{{ s.title || '新对话' }}</button>
              <!-- ··· 菜单按钮 -->
              <button
                @click.stop="toggleMenu(s.session_id)"
                style="flex-shrink:0;padding:4px 8px;background:transparent;border:none;
                       color:#9ca3af;cursor:pointer;font-size:15px;border-radius:4px;
                       letter-spacing:1px;line-height:1"
                @mouseenter="e => e.currentTarget.style.color='#374151'"
                @mouseleave="e => e.currentTarget.style.color='#9ca3af'"
              >···</button>
            </div>

            <!-- 下拉菜单 -->
            <div
              v-if="openMenuId === s.session_id"
              @click.stop
              style="position:absolute;right:4px;top:calc(100% + 2px);z-index:100;
                     background:#fff;border:1px solid #e5e7eb;border-radius:8px;
                     box-shadow:0 4px 12px rgba(0,0,0,0.12);min-width:120px;padding:4px 0"
            >
              <button
                @click="deleteSession(s.session_id)"
                style="width:100%;text-align:left;padding:8px 14px;border:none;
                       background:transparent;font-size:13px;color:#dc2626;cursor:pointer;
                       border-radius:4px"
                @mouseenter="e => e.currentTarget.style.background='#fef2f2'"
                @mouseleave="e => e.currentTarget.style.background='transparent'"
              >删除对话</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧聊天区域 -->
      <div style="flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0">

        <!-- 已收录客户（折叠式） -->
        <div v-if="customers.length"
          style="padding:12px 20px 0;background:#f5f7fa;flex-shrink:0">
          <div class="card" style="margin-bottom:0;padding:12px 16px">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <span style="font-size:12px;color:#6b7280;white-space:nowrap">已收录客户 SIP：</span>
              <span
                v-for="c in customers" :key="c.customer"
                @click="toggleCustomer(c.customer)"
                :title="`${c.doc_count} 份文件 / ${c.part_count} 种零件`"
                style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;
                       border-radius:999px;font-size:12px;cursor:pointer;border:1px solid;transition:all 0.15s"
                :style="activeCustomer === c.customer
                  ? 'background:#4f46e5;color:white;border-color:#4f46e5'
                  : 'background:#eef2ff;color:#4f46e5;border-color:#c7d2fe'"
              >
                {{ c.customer }}
                <span style="font-size:10px;opacity:0.75">{{ c.doc_count }}份</span>
              </span>
            </div>

            <!-- 零件面板 -->
            <div v-if="activeCustomer && customerParts !== null"
              style="margin-top:12px;border-top:1px solid #e5e7eb;padding-top:12px">
              <div v-if="partsLoading" style="color:#9ca3af;font-size:13px">加载中...</div>
              <div v-else-if="!customerParts.length" style="color:#9ca3af;font-size:13px">暂无零件数据</div>
              <div v-else>
                <div style="font-size:12px;color:#6b7280;margin-bottom:8px">
                  {{ activeCustomer }} · 共 {{ customerParts.length }} 条 SIP 记录
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:8px">
                  <div
                    v-for="p in customerParts" :key="p.document_id + p.part_name"
                    style="padding:8px 12px;background:#f9fafb;border:1px solid #e5e7eb;
                           border-radius:8px;font-size:13px;min-width:180px"
                  >
                    <div style="font-weight:500;color:#111827;margin-bottom:2px">{{ p.part_name }}</div>
                    <div style="font-size:11px;color:#6b7280;margin-bottom:6px">
                      {{ p.document_id }} · v{{ p.version }}
                    </div>
                    <a v-if="p.pdf_exists"
                      :href="`/${p.pdf_url}`" target="_blank"
                      style="font-size:12px;color:#4f46e5;text-decoration:none;
                             display:inline-flex;align-items:center;gap:3px"
                    >📄 查看 SIP</a>
                    <span v-else style="font-size:12px;color:#d1d5db">暂无 PDF</span>
                    <button
                      v-if="auth.isAdmin"
                      @click="deleteSip(p.document_id, p.part_name)"
                      style="display:block;margin-top:6px;padding:3px 10px;background:#fee2e2;
                             color:#dc2626;border:1px solid #fca5a5;border-radius:4px;
                             font-size:11px;cursor:pointer"
                    >删除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 聊天消息区 -->
        <div class="chat-box" ref="chatBox"
          style="flex:1;max-height:none;margin:0;border-radius:0;overflow-y:auto;
                 box-shadow:none;background:#f5f7fa;padding:20px">

          <!-- 欢迎页：无消息时显示 -->
          <div v-if="!messages.length" style="padding:8px 0">
            <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;
                        padding:24px 28px;max-width:600px;margin:0 auto 24px">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                <span style="font-size:22px">🤖</span>
                <span style="font-size:16px;font-weight:600;color:#111827">我是 PQM 质量检验知识库助手</span>
              </div>
              <p style="font-size:13px;color:#6b7280;margin:0 0 16px">可以帮助你查询以下内容：</p>
              <div style="display:flex;flex-direction:column;gap:10px">
                <div style="display:flex;align-items:flex-start;gap:12px;padding:12px 14px;
                            background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px">
                  <span style="font-size:18px;line-height:1">🔍</span>
                  <div>
                    <div style="font-size:14px;font-weight:500;color:#111827;margin-bottom:2px">SIP 检验标准查询</div>
                    <div style="font-size:12px;color:#6b7280">查询客户、零件、工序的检验规格、方法和频次</div>
                  </div>
                </div>
                <div style="display:flex;align-items:flex-start;gap:12px;padding:12px 14px;
                            background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px">
                  <span style="font-size:18px;line-height:1">📋</span>
                  <div>
                    <div style="font-size:14px;font-weight:500;color:#111827;margin-bottom:2px">工序异常知识库</div>
                    <div style="font-size:12px;color:#6b7280">检索常见异常的原因分析与对策建议</div>
                  </div>
                </div>
              </div>
            </div>
            <p style="color:#9ca3af;font-size:13px;text-align:center;margin-bottom:12px">你可以这样提问：</p>
            <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:720px;margin:0 auto">
              <button
                @click="sendTip('热压工序出现暗裂是怎么回事，什么原因？')"
                style="padding:6px 14px;background:#fff;border:1px solid #e5e7eb;
                       border-radius:8px;font-size:13px;color:#374151;cursor:pointer;transition:all 0.15s"
                @mouseenter="e => { e.currentTarget.style.background='#eef2ff'; e.currentTarget.style.borderColor='#c7d2fe' }"
                @mouseleave="e => { e.currentTarget.style.background='#fff'; e.currentTarget.style.borderColor='#e5e7eb' }"
              >热压工序出现暗裂是怎么回事，什么原因？</button>
              <button
                @click="sendTip('热压尺寸出现型面超差什么原因，有什么对策？')"
                style="padding:6px 14px;background:#fff;border:1px solid #e5e7eb;
                       border-radius:8px;font-size:13px;color:#374151;cursor:pointer;transition:all 0.15s"
                @mouseenter="e => { e.currentTarget.style.background='#eef2ff'; e.currentTarget.style.borderColor='#c7d2fe' }"
                @mouseleave="e => { e.currentTarget.style.background='#fff'; e.currentTarget.style.borderColor='#e5e7eb' }"
              >热压尺寸出现型面超差什么原因，有什么对策？</button>
            </div>
          </div>

          <div v-for="(msg, i) in messages" :key="i" class="message" :class="msg.role">
            <div class="message-content" v-html="msg.content"></div>
          </div>
          <div v-if="currentLoading" class="message assistant">
            <div class="message-content">
              <div class="loading">
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                {{ thinkingLabel }}
              </div>
            </div>
          </div>
        </div>

        <!-- 输入框 -->
        <div class="input-box"
          style="flex-shrink:0;border-top:1px solid #e5e7eb;border-radius:0;
                 padding:12px 20px;box-shadow:none">
          <input
            v-model="question"
            placeholder="输入你的问题..."
            @keypress.enter="sendMessage"
            :disabled="currentLoading"
          >
          <button v-if="currentLoading" class="btn-danger" @click="stopMessage">⏸ 停止</button>
          <button v-else-if="lastCanceled" class="btn-secondary" @click="resumeLast">▶ 继续上次</button>
          <button v-if="!currentLoading" @click="sendMessage">发送</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, onUnmounted, computed } from 'vue'
import { useChatStore } from '../store/chat'
import { useAuthStore } from '../store/auth'
import NavBar from '../components/NavBar.vue'

const chatStore = useChatStore()
const auth = useAuthStore()

// Per-session reactive state — auto-updates when sessionId changes
const _s = computed(() => chatStore._s(sessionId.value))
const messages       = computed(() => _s.value.messages)
const currentLoading = computed(() => _s.value.isLoading)
const thinkingLabel  = computed(() => _s.value.thinkingLabel)
const lastCanceled   = computed(() => _s.value.lastCanceled)

const question    = ref('')
const sessionId   = ref('')
const chatBox     = ref(null)
const customers   = ref([])
const sessions    = ref([])
const openMenuId  = ref(null)

// 客户零件面板
const activeCustomer = ref(null)
const customerParts  = ref(null)
const partsLoading   = ref(false)

// ··· 下拉菜单
function toggleMenu(sid) {
  openMenuId.value = openMenuId.value === sid ? null : sid
}
function closeMenu() { openMenuId.value = null }
onMounted(() => window.addEventListener('click', closeMenu))
onUnmounted(() => window.removeEventListener('click', closeMenu))

function generateUuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}

async function loadSessions() {
  try {
    const resp = await fetch('/api/v1/agent/sessions?limit=20')
    sessions.value = await resp.json()
  } catch (_) {}
}

async function createSession() {
  const id = generateUuid()
  try {
    await fetch('/api/v1/agent/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: id, title: '' }),
    })
  } catch (_) {}
  sessionId.value = id
  await loadSessions()
}

async function switchSession(id) {
  if (id === sessionId.value) return
  openMenuId.value = null
  sessionId.value = id
  if (!chatStore._ss[id]) {
    try {
      const resp = await fetch(`/api/v1/agent/history/${id}?limit=20`)
      const data = await resp.json()
      if (data.history && data.history.length) {
        chatStore.loadMessages(id, data.history)
      }
    } catch (_) {}
  }
}

onMounted(async () => {
  try {
    const resp = await fetch('/api/v1/upload/customers')
    customers.value = (await resp.json()).customers || []
  } catch (_) {}

  await loadSessions()

  if (sessions.value.length > 0) {
    await switchSession(sessions.value[0].session_id)
  } else {
    await createSession()
  }
})

async function toggleCustomer(name) {
  if (activeCustomer.value === name) {
    activeCustomer.value = null
    customerParts.value = null
    return
  }
  activeCustomer.value = name
  customerParts.value = null
  partsLoading.value = true
  try {
    const resp = await fetch(`/api/v1/upload/customers/${encodeURIComponent(name)}/parts`)
    const data = await resp.json()
    customerParts.value = data.parts || []
  } catch (_) {
    customerParts.value = []
  } finally {
    partsLoading.value = false
  }
}

async function deleteSip(documentId, partName) {
  if (!confirm(`确定要删除 "${partName}" (${documentId}) 的全部 SIP 记录吗？此操作不可撤销。`)) return
  try {
    const resp = await fetch(`/api/v1/upload/sip/${encodeURIComponent(documentId)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${auth.token}` },
    })
    if (!resp.ok) {
      const data = await resp.json()
      alert(`删除失败: ${data.detail || resp.status}`)
      return
    }
    customerParts.value = customerParts.value.filter(p => p.document_id !== documentId)
    if (customerParts.value.length === 0) {
      activeCustomer.value = null
      customerParts.value = null
      const resp2 = await fetch('/api/v1/upload/customers')
      customers.value = (await resp2.json()).customers || []
    }
  } catch (e) {
    alert(`删除失败: ${e.message}`)
  }
}

async function deleteSession(id) {
  openMenuId.value = null
  try {
    await fetch(`/api/v1/agent/history/${id}`, { method: 'DELETE' })
  } catch (_) {}
  chatStore.clearSession(id)
  await loadSessions()
  if (id === sessionId.value) {
    if (sessions.value.length > 0) {
      await switchSession(sessions.value[0].session_id)
    } else {
      await createSession()
    }
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

watch(messages, scrollToBottom, { deep: true })

async function sendMessage() {
  if (!question.value.trim() || currentLoading.value) return
  const q = question.value
  question.value = ''
  chatStore.sendMessage(q, sessionId.value).then(() => loadSessions())
}

function sendTip(text) {
  if (currentLoading.value) return
  question.value = text
  sendMessage()
}

async function stopMessage() {
  await chatStore.cancelCurrent(sessionId.value)
}

async function resumeLast() {
  await chatStore.resumeLast(sessionId.value)
}
</script>
