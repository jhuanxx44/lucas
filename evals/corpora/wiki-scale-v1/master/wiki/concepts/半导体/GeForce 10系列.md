---
title: GeForce 10系列
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: GeForce 10系列是NVIDIA于2016年5月27日发布的图形处理器系列，采用帕斯卡微架构和16nm/14nm工艺，取代GeForce 900系列。该系列涵盖从入门级GT
  1030到旗舰NVIDIA TITAN Xp的桌面和移动GPU，支持Direct3D 12、OpenGL 4.6等API，并引入DisplayPort 1.4、HDMI
  2.0b等特性。移动平台首次移除“M”后缀，性能接近台式机。
source_ids:
- S1
---

# GeForce 10系列

## 概述

GeForce 10系列是英伟达研发并推出的图形处理器系列，用以取代GeForce 900系列。该系列采用帕斯卡微架构，代替之前的麦克斯韦微架构，并采用台积电的16纳米及三星的14纳米FinFET工艺制造。[S1] 发布日期为2016年5月27日。[S1] 产品系列包括GeForce GT和GeForce GTX，涵盖入门级到旗舰级GPU，如GeForce GT 1030、GeForce GTX 1050、GeForce GTX 1080 Ti以及NVIDIA TITAN X和TITAN Xp。[S1] 该系列支持Direct3D 12 (12_1)、OpenGL 4.6、OpenCL 1.2、Vulkan 1.2等API。[S1] 前代产品为GeForce 900系列，后继产品包括GeForce 16系列和GeForce 20系列。[S1]

## 架构特性

GeForce 10系列的微架构命名为帕斯卡，以17世纪法国数学家布莱兹·帕斯卡命名。Nvidia于2016年5月6日召开发布会。[S1] 帕斯卡GPU最高规格采用四组4-Hi HBM2显存，高端消费级显卡显存可达16GB。[S1] 帕斯卡架构的新功能包括：CUDA 6.0 (仅GP100)和6.1、DisplayPort 1.4、HDMI 2.0b、第四代Delta色彩压缩、PureVideo视频解码（支持HEVC Main10、Main12和VP9硬件解码）、HDCP 2.2、NVENC HEVC Main10硬件编码（GP108除外）、GPU Boost 3.0、同时多投影、HB SLI桥接技术、支持GDDR5X和GDDR5的新型内存控制器（仅GP102、GP104）、动态负载均衡调度系统、驱动级别实现三重缓冲（快速同步）。[S1] 从Windows 10 2004版开始，新增对硬件加速GPU计划的支持，减少延迟和提高性能，需WDDM 2.7驱动。[S1]

## 桌面芯片规格

桌面平台显示核心采用GP10x系列芯片，晶体管数从18亿（GP108）到153亿（GP100）不等，制造工艺包括台积电16nm和三星14nm。[S1] 具体型号包括：入门级GeForce GT 1030（GP108，384个流处理器，2GB GDDR5/DDR4，TDP 20-30W）；中端GeForce GTX 1050/1050 Ti/1060（GP107/GP106，流处理器640-1280，显存2-6GB，TDP 75-120W）；高端GeForce GTX 1070/1070 Ti/1080/1080 Ti（GP104/GP102，流处理器1920-3584，显存8-11GB，TDP 150-250W）；旗舰NVIDIA TITAN X和TITAN Xp（GP102，流处理器3584-3840，显存12GB，TDP 250W）。[S1] SLI支持方面，仅TITAN X/Xp、GTX 1080 Ti/1080/1070 Ti/1070支持，其余不支持。[S1] 基于GP102的显卡无DVI插槽，GTX 1080 Ti只有3组DP及一组HDMI。[S1]

## 移动芯片规格

移动平台显示核心的最大亮点是相同规格的性能接近台式机，因此命名中完全删除“M”后缀。全系列GTX移动GPU还具有较低TDP和更安静的Max-Q设计，为超薄游戏笔记本设计。[S1] 移动GPU包括：入门级GeForce MX系列（MX110、MX130、MX150），其中MX150基于GP108，TDP 10-25W；中端GeForce GTX 1050/1050 Ti，TDP 34-64W；高端GeForce GTX 1060/1070/1080，TDP 60-150W，支持SLI。[S1] 移动平台没有GT系列笔记本GPU，而是由MX系列取代。[S1]

## 来源

- [S1] GeForce 10系列 - Wikipedia — https://zh.wikipedia.org/wiki/GeForce_10%E7%B3%BB%E5%88%97（抓取日期：2026-07-27）
