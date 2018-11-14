<template>
    <div>
        <template v-if="loading">
            LOADING ...
        </template>
        <div v-show="!loading">
            <router-view v-on:loading="setLoading"/>
        </div>
    </div>
</template>

<script lang="ts">
    import {Component, Vue} from 'vue-property-decorator';

    @Component
    export default class Portal extends Vue {

        private loading: boolean = true;

        private setLoading(value: boolean) {
            this.loading = value;
        }
    }
</script>

<style lang="scss">
</style>
