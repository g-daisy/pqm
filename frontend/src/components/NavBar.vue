<template>
  <div class="nav">
    <h1 style="display:flex;align-items:center;gap:10px">
      <img src="/logo.png" alt="logo" style="height:36px">
      品质异常分析系统
    </h1>
    <!-- 桌面端导航链接 -->
    <div class="nav-links">
      <router-link to="/chat">💬 对话</router-link>
      <template v-if="auth.isAdmin">
        <router-link to="/upload">📤 上传</router-link>
        <router-link to="/knowledge">📚 知识库</router-link>
        <router-link to="/monitor">📊 监控</router-link>
        <button class="nav-logout-btn" @click="handleLogout">退出登录</button>
      </template>
      <template v-else>
        <router-link to="/login">🔐 管理员</router-link>
      </template>
    </div>
    <!-- 移动端汉堡按钮 -->
    <button class="nav-hamburger" @click.stop="showMenu = !showMenu">
      {{ showMenu ? '✕' : '☰' }}
    </button>
    <!-- 移动端下拉菜单 -->
    <div v-if="showMenu" class="nav-mobile-menu">
      <router-link to="/chat">💬 对话</router-link>
      <template v-if="auth.isAdmin">
        <router-link to="/upload">📤 上传</router-link>
        <router-link to="/knowledge">📚 知识库</router-link>
        <router-link to="/monitor">📊 监控</router-link>
        <button class="nav-logout-btn-mobile" @click="handleLogout">退出登录</button>
      </template>
      <template v-else>
        <router-link to="/login">🔐 管理员</router-link>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'

const auth = useAuthStore()
const router = useRouter()
const showMenu = ref(false)

function handleLogout() {
  showMenu.value = false
  auth.logout()
  router.push('/chat')
}

function closeMenu() { showMenu.value = false }
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>

<style scoped>
.nav-logout-btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.15);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
}
.nav-logout-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

/* 汉堡按钮：默认隐藏，移动端显示 */
.nav-hamburger {
  display: none;
  background: transparent;
  border: none;
  color: white;
  font-size: 22px;
  cursor: pointer;
  padding: 4px 10px;
  margin-left: auto;
  line-height: 1;
}

/* 移动端下拉菜单：默认不渲染（v-if 控制） */
.nav-mobile-menu {
  position: absolute;
  top: 60px;
  left: 0;
  right: 0;
  background: linear-gradient(135deg, #5a3d9a 0%, #4a2d8a 100%);
  display: flex;
  flex-direction: column;
  z-index: 300;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}
.nav-mobile-menu a,
.nav-logout-btn-mobile {
  color: rgba(255, 255, 255, 0.9);
  text-decoration: none;
  padding: 14px 20px;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 15px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  width: 100%;
  transition: background 0.2s;
}
.nav-mobile-menu a:last-child,
.nav-logout-btn-mobile:last-child {
  border-bottom: none;
}
.nav-mobile-menu a:hover,
.nav-logout-btn-mobile:hover {
  background: rgba(255, 255, 255, 0.1);
}
.nav-mobile-menu a.router-link-active {
  background: rgba(255, 255, 255, 0.15);
  color: white;
}

@media (max-width: 768px) {
  /* nav 需要 relative 定位才能锚定下拉菜单 */
  div.nav {
    position: relative;
    overflow: visible;
  }
  /* 隐藏桌面链接，显示汉堡 */
  .nav-links { display: none; }
  .nav-hamburger { display: block; }
  /* 缩小 logo 和标题 */
  h1 {
    font-size: 15px !important;
    flex: 1;
    min-width: 0;
    margin-right: 0 !important;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  h1 img { height: 26px !important; }
}
</style>
