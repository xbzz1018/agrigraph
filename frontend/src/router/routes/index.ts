import type { CustomRoute, ElegantConstRoute, ElegantRoute } from '@elegant-router/types';
import { generatedRoutes } from '../elegant/routes';
import { layouts, views } from '../elegant/imports';
import { transformElegantRoutesToVueRoutes } from '../elegant/transform';

/**
 * custom routes
 *
 * @link https://github.com/soybeanjs/elegant-router?tab=readme-ov-file#custom-route
 */
const customRoutes: CustomRoute[] = [
  {
    name: 'knowledge-base-detail',
    path: '/knowledge-base/:id',
    component: 'layout.base$view.knowledge-base-detail',
    props: true,
    meta: {
      title: '病虫害详情',
      hideInMenu: true,
      activeMenu: 'knowledge-base'
    }
  } as CustomRoute
];

/** create routes when the auth route mode is static */
export function createStaticRoutes() {
  const constantRoutes: ElegantRoute[] = [];

  const authRoutes: ElegantRoute[] = [];

  const focusedRouteNames = new Set(['chat', 'knowledge-base', 'knowledge-graph', 'diagnosis', 'agent-runs']);
  [...customRoutes, ...generatedRoutes.filter(item => focusedRouteNames.has(item.name))].forEach(item => {
    if (item.meta?.constant) {
      constantRoutes.push(item);
    } else {
      authRoutes.push(item);
    }
  });

  return {
    constantRoutes,
    authRoutes
  };
}

/**
 * Get auth vue routes
 *
 * @param routes Elegant routes
 */
export function getAuthVueRoutes(routes: ElegantConstRoute[]) {
  return transformElegantRoutesToVueRoutes(routes, layouts, {
    ...views,
    'knowledge-base-detail': () => import('@/views/knowledge-base/detail.vue')
  });
}
