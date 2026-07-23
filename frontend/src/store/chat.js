import { defineStore } from 'pinia'
import axios from 'axios'
import { marked } from 'marked'
import { chatApi } from '../api/chat'

marked.setOptions({ breaks: true })

function renderMarkdown(text) {
  return marked.parse(text || '')
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

function initSession() {
  return {
    messages: [],
    isLoading: false,
    isTyping: false,
    thinkingLabel: '正在思考...',
    lastCanceled: false,
    _controller: null,
    _typewriterTimer: null,
  }
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    _ss: {},  // { [sessionId]: SessionState }
  }),

  actions: {
    // Returns or lazily initialises the session state object.
    _s(sid) {
      if (!this._ss[sid]) {
        this._ss[sid] = initSession()
      }
      return this._ss[sid]
    },

    // Inject history loaded from DB into a session (called by switchSession on first load).
    loadMessages(sid, messages) {
      const s = this._s(sid)
      s.messages = messages.map(m => ({
        role: m.role,
        content: m.role === 'assistant' ? renderMarkdown(m.content) : m.content,
      }))
    },

    _startTypewriter(sid, msgIndex, rawText, pdfUrls) {
      const BATCH = 4
      const INTERVAL = 16

      const s = this._s(sid)
      s.isTyping = true
      let charIndex = 0

      s._typewriterTimer = setInterval(() => {
        charIndex = Math.min(charIndex + BATCH, rawText.length)
        const slice = rawText.slice(0, charIndex)
        s.messages[msgIndex].content = escapeHtml(slice)

        if (charIndex >= rawText.length) {
          clearInterval(s._typewriterTimer)
          s._typewriterTimer = null

          let finalContent = renderMarkdown(rawText)
          if (pdfUrls && pdfUrls.length > 0) {
            const pdfs = pdfUrls.map(url =>
              `<a href="/${url}" target="_blank">📥 ${url}</a>`
            ).join('')
            finalContent += `<div class="pdf-links">📄 相关文档: ${pdfs}</div>`
          }
          s.messages[msgIndex].content = finalContent
          s.isTyping = false
        }
      }, INTERVAL)
    },

    async sendMessage(question, sid) {
      const s = this._s(sid)
      if (s.isLoading || s.isTyping) return

      s.isLoading = true
      s.lastCanceled = false
      s.thinkingLabel = '正在思考...'
      s.messages.push({ role: 'user', content: question })

      const controller = new AbortController()
      s._controller = controller

      try {
        await chatApi.queryStream(
          question,
          sid,
          // onThinking
          (event) => {
            s.thinkingLabel = event.label
          },
          // onDone
          (event) => {
            s.isLoading = false
            s._controller = null

            if (event.cancelled) {
              s.messages.push({ role: 'assistant', content: '⏸ 已停止。可以「继续上次」或换一个新问题。', isCanceled: true })
              s.lastCanceled = true
              return
            }

            const rawText = event.answer || ''
            const pdfUrls = event.pdf_urls || []
            const msgIndex = s.messages.length
            s.messages.push({ role: 'assistant', content: '' })
            this._startTypewriter(sid, msgIndex, rawText, pdfUrls)
          },
          // onError
          (error) => {
            s.isLoading = false
            s._controller = null
            s.messages.push({ role: 'assistant', content: `❌ 请求失败: ${error}`, isError: true })
          },
          controller.signal,
        )
      } catch (error) {
        s.isLoading = false
        s._controller = null
        if (error.name === 'AbortError') {
          s.messages.push({ role: 'assistant', content: '⏸ 已停止。可以「继续上次」或换一个新问题。', isCanceled: true })
          s.lastCanceled = true
        } else {
          s.messages.push({ role: 'assistant', content: `❌ 请求失败: ${error.message}`, isError: true })
        }
      }
    },

    async cancelCurrent(sid) {
      const s = this._s(sid)
      if (!s.isLoading) return
      try {
        await chatApi.cancel(sid)
      } catch (e) {}
      if (s._controller) {
        s._controller.abort()
      }
    },

    async resumeLast(sid) {
      const s = this._s(sid)
      if (s.isLoading) return
      s.isLoading = true
      s.lastCanceled = false
      s.thinkingLabel = '正在恢复上次查询...'

      const controller = new AbortController()
      s._controller = controller

      try {
        const response = await chatApi.resume(sid, controller.signal)
        const data = response.data
        if (data.cancelled) {
          s.messages.push({ role: 'assistant', content: '⏸ 已停止。可以「继续上次」或换一个新问题。', isCanceled: true })
          s.lastCanceled = true
        } else if (data.error) {
          s.messages.push({ role: 'assistant', content: `❌ 错误: ${data.error}`, isError: true })
        } else {
          s.messages.push({ role: 'assistant', content: renderMarkdown(data.answer || '') })
        }
      } catch (error) {
        if (axios.isCancel(error) || error.name === 'CanceledError') {
          s.messages.push({ role: 'assistant', content: '⏸ 已停止。可以「继续上次」或换一个新问题。', isCanceled: true })
          s.lastCanceled = true
        } else {
          s.messages.push({ role: 'assistant', content: `❌ 继续失败: ${error.message}`, isError: true })
        }
      } finally {
        s.isLoading = false
        s._controller = null
      }
    },

    // Clear a session's in-memory state (also called on delete).
    clearSession(sid) {
      const s = this._ss[sid]
      if (!s) return
      if (s._typewriterTimer) {
        clearInterval(s._typewriterTimer)
      }
      delete this._ss[sid]
    },
  },
})
