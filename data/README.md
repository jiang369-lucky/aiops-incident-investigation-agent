# 数据说明

本项目使用 LogPAI 的 Loghub OpenStack 数据，只用于研究和学习。数据下载地址：
https://zenodo.org/records/3227177/files/OpenStack.tar.gz?download=1

- 版本：Zenodo record 3227177，v7
- 归档文件：`OpenStack.tar.gz`
- 官方 MD5：`66bd42c07837a094d9b0ea2d036b5713`
- 原始内容：`openstack_abnormal.log`、`openstack_normal1.log`、
  `openstack_normal2.log`、`anomaly_labels.txt`
- 标签语义：`anomaly_labels.txt` 只给出异常虚拟机实例 ID，不是逐行根因标签。

原始数据不会提交到 Git。执行 `scripts/download_data.ps1` 或
`scripts/download_data.sh` 可重新下载并校验。
