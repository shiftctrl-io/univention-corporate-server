<template>
    <div>{{ entry.title }}</div>
</template>

<script lang="ts">
    import {Component, Vue, Prop} from 'vue-property-decorator';
    import {EntryData} from "../types";

    @Component
    export default class Tile extends Vue {
        @Prop()
        entry!: EntryData
    }
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped lang="scss">
</style>
