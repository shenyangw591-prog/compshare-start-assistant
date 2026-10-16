# 公开发布指南

## 上传 GitHub

1. 建议仓库名 `compshare-start-assistant`，简介可填「优云智算 GPU 实例自动开机助手 · 中文图形界面 · 离线演示 · 可加密记住密钥」。
2. 解压源码包，上传里面的文件。通过网页上传时也要包含 `.github` 和 `.gitignore`；使用 Git 提交整个源码目录可以保留它们。
3. 仓库已准备 MIT LICENSE，不需要另外生成。请勿上传自己的 `config.json`、API 密钥、账户截图或含有敏感信息的日志。
4. 在 Releases 中创建 `v0.4.6`，附上 Windows ZIP 和 `SHA256SUMS.txt`。普通用户从 Release 下载即可，不需要 Git 或 Python。
5. README 用的是相对图片与文档路径，不依赖作者的仓库名。上传后检查首页截图正常显示。

本地 `release/` 内的包已做好文件筛选。源码目录之外的训练资料和实验文件不属于本项目，不要连同上传。

## 后续构建

开发机器安装 Python 3.11 或以上，运行：

```bash
python -m pip install -r requirements-build.txt
python -m unittest -v test_start_instance.py test_gui.py test_credential_store.py
python build_release.py
```

也可以在 GitHub Actions 页面手动运行 `Build Windows release`。工作流执行离线测试并生成可下载的产物，不需要填写任何云平台密钥。

## 交流群分享文案

> 做了一个优云智算开机助手，适合已有实例因为缺卡而开不了机时使用。中文界面，填 API 公钥/私钥 → 选实例 → 开始等待，资源不足会自动重试，确认运行后停止、弹出成功提示并响铃。可勾选记住密钥，Windows 本机加密保存，下次自动填入，也可随时清除。内置离线演示，不会操作的可以先试一遍。Windows 免安装版，解压双击即可。社区工具，非官方出品，不能保证一定抢到；开机后正常计费，用完记得关机。目前已完成离线测试，欢迎反馈实测情况，反馈时请勿发送密钥。

分享时附上 Windows ZIP 和你的仓库地址即可。首发仍建议先用自己的实例完成一次真实 API 联调。
