<script setup lang="ts">
import { computed } from "vue";
import { withBase } from "vitepress";

const props = defineProps<{
  src: string;
  title: string;
}>();

const videoUrl = computed(() => withBase(props.src));
</script>

<template>
  <figure class="cgat-video">
    <video controls playsinline preload="metadata" :aria-label="title">
      <source :src="videoUrl" type="video/mp4">
      Your browser does not support HTML5 video.
    </video>
    <figcaption>
      <span>{{ title }}</span>
      <a :href="videoUrl">打开原视频</a>
    </figcaption>
  </figure>
</template>
