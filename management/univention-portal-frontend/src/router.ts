import Vue from 'vue';
import Router from 'vue-router';
import Portal from './views/Portal.vue';

Vue.use(Router);

export default new Router({
  mode: 'history',
  base: process.env.BASE_URL,
  routes: [
    {
      path: '/',
      name: 'portal',
      component: Portal,
    },
  ],
});
