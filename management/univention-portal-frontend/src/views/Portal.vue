<template>
    <div>
        <div class='portal-header'>
            {{ portal.title }}
        </div>
        <div class='portal-body'>
            <template v-for='content_e in portal.content'>
                <div>{{ content_e[0].title }}</div>
                <div v-for="entry in content_e[1]">{{ entry.title }}</div>
            </template>
        </div>

    </div>
</template>

<script lang='ts'>
    import {Component, Vue} from 'vue-property-decorator';
    import services from '../services';
    import {CategoryData, CategoryType, EntryData, EntryType, PortalData, PortalType} from '../types';

    @Component
    export default class Portal extends Vue {
        private portalO: PortalData = {title_localized: '', content: []};
        private categories: CategoryData = {};
        private entries: EntryData = {};

        get portal(): PortalType {
            const portal = {title: '', content: []} as PortalType;
            portal.title = this.portalO.title_localized;
            portal.content = this.portalO.content.map(([cCn, eDns]): [CategoryType, EntryType[]] => {
                return [
                    {title: this.categories[cCn].title_localized},
                    eDns.map((eDn) => {
                        return {title: this.entries[eDn].title_localized};
                    }),
                ];
            });
            return portal;
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
