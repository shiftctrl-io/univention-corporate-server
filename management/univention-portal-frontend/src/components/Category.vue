<template>
    <div>
        <h3>{{ category[0].title }}</h3>
        <Tile v-for='entry in category[1]'
            v-bind:entry="entry"
        />
    </div>
</template>

<script lang="ts">
    import {Component, Vue, Prop} from 'vue-property-decorator';
    import { ContentEntry } from "../types";
    import Tile from './Tile.vue';

    @Component({
        components: {
            Tile
        }
    })
    export default class Category extends Vue {
        @Prop()
        category!: ContentEntry
    }
</script>


<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped lang="scss">
</style>
