<template>
    <div>
        <h2>{{category.display_name_localized}}</h2>
        <Entry v-for="(entry, index) in entries" v-bind:key="index" v-bind:entry="entry"/>
    </div>
</template>

<script>
// @flow

import Entry from './Entry'
export default {
    name: 'Category',
    props: ['category', 'entries'],
    components: {Entry}
}
</script>

<style scoped>

</style>
