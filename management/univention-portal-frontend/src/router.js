// @flow
import Vue from 'vue'
import Router from 'vue-router'
import Portal from './views/Portal.vue'
import NProgress from 'nprogress'

Vue.use(Router);

const router =  new Router({
    mode: 'history',
    base: process.env.BASE_URL,
    routes: [
        {
            path: '/',
            name: 'portal',
            component: Portal
        }
    ]
});

router.beforeEach((to, from, next) => {
    NProgress.start();
    next()
});
export default router
