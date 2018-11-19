<template>
    <div>
        <h1>{{ portal.title_localized }}</h1>
        <Category v-for="(section, index) in categoryOrdered" v-bind:key="index" v-bind:category="section.category"
                  v-bind:entries="section.entries"/>
    </div>
</template>

<script>
// @flow
import NProgress from 'nprogress'
import Category from '../components/Category'

/*::
import type {Dn, CategoryDatum, EntryDatum} from "../flow_types";
*/

export default {
    name: "Portal",
    components: {Category},
    data: function () {
        return {
            portal: {},
            categories: {},
            entries: {}
        }
    },
    computed: {
        categoryOrdered: function () {
            const result = [];
            if (!this.portal.content) {
                return result
            }
            this.portal.content.forEach((value) => {
                result.push({
                    category: this.categories[value[0]],
                    entries: value[1].map((e_dn) => {
                        return this.entries[e_dn]
                    })
                });
            });
            return result;
        }
    },
    created: async function () {
        const result = await Promise.all([
            this.$service.getPortal(),
            this.$service.getCategories(),
            this.$service.getEntries()
        ]);
        this.portal = result[0];
        this.categories = result[1];
        this.entries = result[2];
        NProgress.done();
    }
}
</script>

<style scoped>

</style>
