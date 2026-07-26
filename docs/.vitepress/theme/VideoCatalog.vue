<script setup lang="ts">
import { computed } from "vue";
import { withBase } from "vitepress";
import { tutorialVideos } from "../data/videos";

const props = withDefaults(defineProps<{ showPlanned?: boolean }>(), {
  showPlanned: false
});

const groups = computed(() => {
  const grouped = new Map<string, typeof tutorialVideos>();
  for (const video of tutorialVideos) {
    if (!props.showPlanned && video.status !== "published") continue;
    const records = grouped.get(video.section) || [];
    records.push(video);
    grouped.set(video.section, records);
  }
  return [...grouped.entries()];
});
</script>

<template>
  <div class="video-catalog">
    <section v-for="([section, videos]) in groups" :key="section">
      <h2>{{ section }}</h2>
      <ul>
        <li v-for="video in videos" :key="video.id">
          <a :href="withBase(video.page)">
            <span class="video-number">{{ video.number }}</span>
            <span>{{ video.title }}</span>
          </a>
          <span v-if="video.status === 'planned'" class="video-status">准备中</span>
        </li>
      </ul>
    </section>
  </div>
</template>
