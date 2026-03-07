import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Inbox from './views/Inbox.vue'
import Message from './views/Message.vue'
import Thread from './views/Thread.vue'
import Search from './views/Search.vue'
import NotFound from './views/NotFound.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/inbox/:name', component: Inbox, props: true },
  { path: '/message/:id(.*)', component: Message, props: true },
  { path: '/thread/:id(.*)', component: Thread, props: true },
  { path: '/search', component: Search },
  { path: '/:pathMatch(.*)*', component: NotFound },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
