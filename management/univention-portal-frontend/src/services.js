// @flow

import {fetchCategories, fetchEntries, fetchPortal} from "./fetchApi";
/*::
import Vue from 'vue'
*/

export default {
    install: function(Vue/*: Vue*/) {
        Vue.prototype.$service = this;
    },
    getPortal: async function() {
        return fetchPortal()
    },
    getCategories: async function() {
        return fetchCategories()
    },
    getEntries: async function() {
        return fetchEntries()
    }
}
