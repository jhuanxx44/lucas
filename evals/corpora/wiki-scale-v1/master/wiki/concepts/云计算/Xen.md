---
title: Xen
type: concept
industry: 云计算
as_of: '2026-07-27'
summary: Xen 是开源虚拟机监视器，由 Xen Project 开发，能在单台计算机上运行多达 128 个操作系统。它通过半虚拟化技术实现高性能，并支持
  Intel VT-x 和 AMD-V 的完全虚拟化。Xen 支持实时迁移，常用于云计算基础设施。2013 年成为 Linux 基金会合作项目。
source_ids:
- S1
---

# Xen

**Xen** 是开放源代码虚拟机监视器，由 Xen Project 开发，能够在单个计算机运行多达 128 个有完全功能的操作系统 [S1]。

## 概述与历史
Xen 最初由凯伊尔·弗拉瑟、史蒂芬·汉特和伊安·普拉特在剑桥大学计算机实验室开发，于 2003 年首次发布。当前版本为 4.16，于 2021 年 12 月 2 日发布 [S1]。Xen 采用 GNU GPL v2 许可协议，支持 Linux、BSD 和 OpenSolaris 操作系统 [S1]。2013 年 4 月，Linux 基金会宣布 Xen 成为 Linux 基金会合作项目 [S1]。

## 技术特点
### 半虚拟化
Xen 通过半虚拟化技术获得高效能表现，典型情况下性能损失约 2%，最糟情况下约 8%；相比之下，其他完全虚拟化方案可能造成高达 20% 的损耗 [S1]。半虚拟化要求客户端操作系统经过修改以与 Xen API 连接。目前支持修改的操作系统包括 NetBSD、GNU/Linux、FreeBSD 和贝尔实验室的 Plan 9 系统。Novell 展示了 NetWare 与 Xen 的连通，Sun 微系统公司也在研究 Solaris 的连通 [S1]。

### 完全虚拟化
若处理器支持虚拟硬件扩展（Intel VT-x 或 AMD-V），Xen 允许运行未经修改的操作系统（如 Windows），性能也有提升。Xen 的完全虚拟化依赖于 QEMU [S1]。

## 功能特性
### 虚拟机迁移
Xen 支持在物理主机之间即时迁移虚拟机，无需停止虚拟机。迁移过程中内存被反复复制到目标机器，最终同步时会有 60-300 毫秒的短暂暂停，实现无缝迁移 [S1]。

### 系统平台支持
Xen 目前可运行在 x86 和 x86-64 系统上 [S1]。

## 类 Unix 系统的 Xen 支持
- Red Hat 的 RHEL 及其衍生版本（如 CentOS）从 RHEL 6 开始已使用 KVM 作为默认虚拟化技术 [S1]。
- Debian、Ubuntu、FreeBSD、OpenBSD、NetBSD 均支持 Xen [S1]。

## 使用场景
IBM 经常在主机和服务器上使用 Xen 以提升性能和安全性，例如通过隔离的虚拟 OS 增强安全性，或使不同操作系统在同一台计算机上运行。Xen 还支持运行时迁移，保证正常运行且避免宕机 [S1]。

## 来源

- [S1] Xen - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Xen（抓取日期：2026-07-27）
