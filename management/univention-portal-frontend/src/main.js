// @flow
import Vue from 'vue'
import App from './App.vue'
import router from './router'
import service from './services';

import '../node_modules/nprogress/nprogress.css'

Vue.config.productionTip = false;
Vue.use(service);

new Vue({
    router,
    render: h => h(App)
}).$mount('#app');
