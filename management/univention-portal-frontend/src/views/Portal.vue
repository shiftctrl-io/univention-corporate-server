<template>
    <div>
        <div class='portal-header'>
            {{ portal.title }}
        </div>
        <div class='portal-body'>
            <Category
                v-for='content_e in portal.content'
                v-bind:category="content_e"
            />
        </div>
    </div>
</template>

<script lang='ts'>
    import {Component, Vue} from 'vue-property-decorator';
    import services from '../services';
    import {CategoryData, CategoryType, EntryData, EntryType, PortalData, PortalType} from '../types';
    import Category from '../components/Category.vue';

    @Component({
        components: {Category}
    })
    export default class Portal extends Vue {
        private portalO: PortalData = {title_localized: '', content: []};
        private categories: CategoryData = {};
        private entries: EntryData = {};

        get portal(): PortalType {
            return {
                title: this.portalO.title_localized,
                content: this.portalO.content.map(([cCn, eDns]): [CategoryType, EntryType[]] => {
                    return [
                        {title: this.categories[cCn].title_localized},
                        eDns.map((eDn) => {
                            return {title: this.entries[eDn].title_localized};
                        }),
                    ];
                }),
            };
        }

        protected created() {
            const promises: [Promise<PortalData>,
                Promise<CategoryData>, Promise<EntryData>] = [
                services.getPortal(),
                services.getCategories(),
                services.getEntries(),
            ];
            Promise.all(promises).then((values) => {
                [this.portalO, this.categories, this.entries] = values;
                this.$emit('loading', false);
            });
        }
    }
</script>
