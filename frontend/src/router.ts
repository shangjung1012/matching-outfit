import { createRouter, createWebHistory } from 'vue-router'
import type { AppView } from './types'

const routes: Array<{ path: string; name: AppView; alias?: string | string[] }> = [
  { path: '/find_outfit', name: 'agent' },
  { path: '/find_similarity', name: 'similarity' },
  { path: '/virtual_tryon', name: 'tryon' },
  { path: '/clothes_catalog', name: 'catalog' },
  { path: '/outfit_article', name: 'knowledge' },
  { path: '/my_favorites', name: 'favorites' },
  { path: '/my_preference', name: 'preferences', alias: '/my_profile' },
  { path: '/outfit-mbti', name: 'mbti' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...routes.map((route) => ({
      ...route,
      // MainApp.vue owns the actual rendering; the router only tracks which
      // view is active in the URL, so every route resolves to an empty shell.
      component: { render: () => null },
    })),
    { path: '/', redirect: '/find_outfit' },
    { path: '/:pathMatch(.*)*', redirect: '/find_outfit' },
  ],
})
