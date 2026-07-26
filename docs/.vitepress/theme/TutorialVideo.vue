<script setup lang="ts">
import { computed } from "vue";
import VideoPlayer from "./VideoPlayer.vue";
import { findTutorialVideo } from "../data/videos";

const props = defineProps<{ id: string }>();
const video = computed(() => findTutorialVideo(props.id));
</script>

<template>
  <VideoPlayer
    v-if="video?.status === 'published' && video.src"
    :src="video.src"
    :title="`${video.number} ${video.title}`"
  />
  <div v-else-if="video" class="status-card">
    <strong>{{ video.number }} {{ video.title }}</strong>：视频正在准备中。
  </div>
  <div v-else class="status-card">未找到视频条目：{{ id }}</div>
</template>
