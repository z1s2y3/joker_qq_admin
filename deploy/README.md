# 云服务器部署

项目预期运行在 Linux 云服务器上，使用 systemd 保持官方 QQ 机器人常驻运行。部署包只包含代码和功能配置，不包含 Windows 端的群组、签到、抽奖、回复或数据库数据。

## 手动部署

```bash
sudo JOKER_QQ_ADMIN_DIR=/opt/joker_qq_admin bash deploy/install.sh
sudo nano /etc/joker_qq_admin/joker_qq_admin.env
sudo JOKER_QQ_ADMIN_DIR=/opt/joker_qq_admin bash deploy/install.sh
sudo systemctl restart joker-qq-admin
sudo journalctl -u joker-qq-admin -f
```

Windows 可使用上传脚本传输正式程序文件，不会上传本地数据或 `.env`：

```powershell
.\deploy\upload.ps1 -HostName 服务器地址 -UserName root -KeyPath C:\密钥\server_ed25519
```

脚本执行前需要先在云服务器准备 Python 3.11+、`sudo`、`systemd` 和 OpenSSH 服务。当前工作区没有云服务器地址和 SSH 私钥，因此不会在本机直接发起上传。

环境文件至少包含：

```text
QQBOT_APP_ID=
QQBOT_APP_SECRET=

# 可选功能配置
SCUM_RELAY_URL=https://ba.yooyun.top
SCUM_RELAY_KEY=
JOKER_QQ_DATA_DIR=/var/lib/joker_qq_admin
```

环境文件权限应保持为 `600`，不能放进 Git 或部署压缩包。`JOKER_QQ_DATA_DIR` 指向 Linux 云服务器上的运行数据目录；该目录由官方机器人和 Linux 端共同维护时，必须保证服务用户有读写权限。

首次启动会在 `JOKER_QQ_DATA_DIR` 创建空的 SQLite 数据库，不会从 Windows 端导入旧数据。

