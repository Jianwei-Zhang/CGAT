# CGAT 文档站部署指南

正式地址：`https://riceome.hzau.edu.cn/cgat/`

服务器目录：`/home/xbzhang/cgat_docs/`

## 本地构建

在仓库根目录执行：

```bash
npm ci
npm run docs:build:web
```

构建命令会先校验文档和视频目录，再生成适用于 `/cgat/` 路径的完整静态站：

```text
docs/web/
```

确认入口文件存在：

```bash
test -f docs/web/index.html
```

## 打包与手动上传

在仓库根目录把站点内容打包。压缩包内直接包含 `index.html`，不会额外包含一层 `web/` 目录：

```bash
tar -C docs/web -czf docs/cgat_docs.tar.gz .
```

通过浏览器或其他文件传输工具，把下面这个文件上传到服务器的 `/home/xbzhang/`：

```text
docs/cgat_docs.tar.gz
```

登录目标服务器后创建目录并解压：

```bash
mkdir -p /home/xbzhang/cgat_docs
tar -xzf /home/xbzhang/cgat_docs.tar.gz -C /home/xbzhang/cgat_docs
test -f /home/xbzhang/cgat_docs/index.html
```

## Nginx

在 `/home/Software/nginx/conf/nginx.conf` 的 `riceome.hzau.edu.cn` HTTPS `server` 块内，放在现有 `location /` 前面：

```nginx
location = /cgat {
    return 301 /cgat/;
}

location ^~ /cgat/ {
    alias /home/xbzhang/cgat_docs/;
    index index.html;
    autoindex off;
    try_files $uri $uri.html $uri/ =404;
}
```

`^~` 确保 `/cgat/` 下的文件不会落入该站点已有的正则 location 或根路径反向代理。

修改配置后由有权限的管理员执行：

```bash
/home/Software/nginx/sbin/nginx -t -c /home/Software/nginx/conf/nginx.conf
/home/Software/nginx/sbin/nginx -s reload
```

## 验收

```bash
curl -I https://riceome.hzau.edu.cn/cgat
curl -I https://riceome.hzau.edu.cn/cgat/
curl -I https://riceome.hzau.edu.cn/cgat/zh/guide/overview
curl -I https://riceome.hzau.edu.cn/cgat/logo.svg
```

预期 `/cgat` 返回 301，其他地址返回 200。确认新站正常后，再把 GitHub Pages 入口改成跳转到正式地址。
