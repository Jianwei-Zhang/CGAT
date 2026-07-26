import DefaultTheme from "vitepress/theme";
import TutorialVideo from "./TutorialVideo.vue";
import VideoCatalog from "./VideoCatalog.vue";
import VideoPlayer from "./VideoPlayer.vue";
import "./style.css";

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component("VideoPlayer", VideoPlayer);
    app.component("TutorialVideo", TutorialVideo);
    app.component("VideoCatalog", VideoCatalog);
  }
};
