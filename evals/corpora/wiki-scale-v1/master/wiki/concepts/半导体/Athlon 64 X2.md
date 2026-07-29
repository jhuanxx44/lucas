---
title: Athlon 64 X2
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: AMD Athlon 64 X2是AMD于2005年5月推出的首款桌面双核处理器，采用K8微架构，支持Socket 939和AM2，制程包括90nm和65nm，核心代号包括Toledo、Manchester、Windsor、Brisbane等，主频范围1.0-3.2GHz，L2缓存每核256KB至1024KB，支持MMX、SSE2、SSE3、x86-64等指令集。
source_ids:
- S1
---

# Athlon 64 X2

## 概述

**Athlon 64 X2** 是 AMD 设计的首款桌面级双核心处理器，于2005年5月首次推出，脚位包括 Socket 939 和 Socket AM2 [S1]。首批产品采用90nm SOI 制程，其后推出代号 **Brisbane** 的65nm产品，于2006年12月发售 [S1]。处理器内建两颗 Athlon 64 核心，两个核心通过 **System Request Queue** 互相沟通，相比 Intel Pentium D 通过FSB绕道北桥通信的方式，性能更高但售价较贵 [S1]。

## 技术特点

Athlon 64 X2 的微架构为 AMD K8，部分后期型号也使用 K10 微架构 [S1]。支持的指令集包括 MMX、SSE、SSE2、SSE3、x86-64、3DNow!，以及部分型号支持的 AMD-V 虚拟化技术 [S1]。制程工艺从 90nm 过渡到 65nm，核心数量为2，CPU 主频范围 1.0GHz 至 3.2GHz，HyperTransport 速率 1000MT/s 至 1800MT/s [S1]。

与单核心 Athlon64 相比，双核产品拥有更多的晶体管，晶圆需使用更复杂的制程，导致产量较低、售价更贵 [S1]。由于对外连接采用 HyperTransport，与 Athlon 64 相同，使用 Socket 939 或 Socket AM2 单核 Athlon 64 的用户只需更新主板 BIOS 即可直接升级为 Athlon 64 X2 [S1]。

早期 Athlon X2 处理器有 2×512 KB 及 2×1024 KB 两种 L2 缓存版本，2006年中 AMD 宣布停产 2×1024 KB L2 的 Athlon X2 [S1]。此外有低阶 X2 3600+ 型号，时脉与 3800+ 相同，但 L2 减为 2×256 KB，最初仅提供 OEM 厂商，后为应对 Intel Core 2 上市，AMD 于2006年7月至8月发行 AM2 版本 3600+ 与 Intel Pentium D 915/925 竞争 [S1]。

AMD 于2006年12月发售65nm产品，代号 Brisbane，仍使用 K8 微架构，而使用 K10 微架构的新产品预计于2007年中推出 [S1]。2007年6月推出的 Brisbane 45W BE 省电版本双核处理器改称为「Athlon X2」，去掉 "64" 字样，并使用全新型号，如 BE-2350、BE-2400 [S1]。部分双核产品属 Black Edition 黑盒版本，不锁倍频，包括 90nm F3 步进的 6400+ 及 65nm G2 步进的 5400+、5000+ [S1]。

## 核心与型号列表

### Athlon 64 X2 核心

#### Toledo (90nm SOI)
- 双核心处理器，CPU 步进 E6 [S1]
- L1 缓存：每核 64+64 KB（数据+指令） [S1]
- L2 缓存：每核 512/1024 KB 全速 [S1]
- 支持 MMX、Extended 3DNow!、SSE、SSE2、SSE3、AMD64、Cool'n'Quiet、NX Bit [S1]
- Socket 939，HyperTransport (1000MHz) [S1]
- 核心电压 1.3V-1.35V，TDP 89W 或 110W [S1]
- 时脉 2000-2400MHz [S1]
- 型号包括 3800+ (2000MHz, 512KB×2)、4200+ (2200MHz, 512KB×2)、4400+ (2200MHz, 1024KB×2)、4600+ (2400MHz, 512KB×2)、4800+ (2400MHz, 1024KB×2) [S1]

#### Manchester (90nm SOI)
- 双核心处理器，CPU 步进 E4、E6 [S1]
- L1 缓存：每核 64+64 KB [S1]
- L2 缓存：每核 256/512 KB 全速 [S1]
- 支持指令集同 Toledo [S1]
- Socket 939，HyperTransport (1000MHz) [S1]
- 核心电压 1.35V-1.4V，TDP 最大 89W [S1]
- 时脉 2000-2400MHz [S1]
- 型号包括 3600+ (2000MHz)、3800+ (2000MHz)、4200+ (2200MHz)、4600+ (2400MHz) [S1]

#### Windsor (90nm SOI)
- 双核心处理器，CPU 步进 F2、F3 [S1]
- L1 缓存：每核 64+64 KB [S1]
- L2 缓存：每核 512/1024 KB [S1]
- 支持 MMX、Extended 3DNow!、SSE、SSE2、SSE3、AMD64、Cool'n'Quiet、NX Bit、AMD Virtualization（3800+ EE SFF 35W 独有） [S1]
- Socket AM2，HyperTransport (1000MHz) [S1]
- 核心电压 1.30V-1.35V (89W)，TDP 有 35W (3800+ EE SFF)、65W (3600+ 至 4800+)、89W (5000+ 至 5600+)、125W (6000+ 至 6400+) [S1]
- 首次发行：2006年5月23日 [S1]
- 时脉 2000-3200MHz [S1]
- 型号包括 3600+ (2000MHz, 256KB×2)、3800+ (2000MHz, 512KB×2)、4000+ (2000MHz, 1024KB×2) 至 6400+ (3200MHz, 1024KB×2) [S1]
- 2006年6月中 AMD 宣布不再出产每核1MB L2 的 Athlon 64 X2，仅出产少量 2×1MB L2 的 4000+、4400+、4800+ [S1]

#### Brisbane (65nm SOI)
- CPU 步进 G1、G2 [S1]
- L1 缓存：每核 64+64 KB [S1]
- L2 缓存：每核 512 KB 全速 [S1]
- 支持 MMX、Extended 3DNow!、SSE、SSE2、SSE3、AMD64、Cool'n'Quiet、NX Bit、AMD-V [S1]
- Socket AM2，HyperTransport (1000MHz) [S1]
- 核心电压 1.25V-1.35V，TDP 65W~89W [S1]
- 首次发行：2006年12月5日 [S1]
- 时脉 1900-3100MHz [S1]
- 型号包括 3600+ (1900MHz) 至 6000+ (3100MHz) [S1]

#### Kuma (65nm SOI)
- CPU 步进 B3 [S1]
- L1 缓存：每核 64+64 KB [S1]
- L2 缓存：每核 512 KB 全速，L3 缓存：2 MB 共享 [S1]
- 支持 MMX、Extended 3DNow!、SSE、SSE2、SSE3、SSE4A、AMD64、Cool'n'Quiet、NX Bit、AMD-V [S1]
- Socket AM2+，HyperTransport (3200MHz) [S1]
- 核心电压 1.25V，TDP 95W [S1]
- 首次发行：2008年9月2日 [S1]
- 时脉 2300-2800MHz [S1]
- 型号包括 6500BE (2100MHz)、7450、7550、7750、7750BE、7850BE [S1]

### Athlon X2 BE 45W 系列

#### Brisbane (65nm SOI)
- 45W 低功耗版本，CPU 步进 G1、G2 [S1]
- L1/L2 缓存同上，支持 AMD-V [S1]
- Socket AM2，HyperTransport (1000MHz) [S1]
- 核心电压 1.25V，TDP 45W [S1]
- 首次发行：2007年6月1日 [S1]
- 时脉 1900-2600MHz [S1]
- 型号包括 BE-2300 (1900MHz)、BE-2350 (2100MHz)、BE-2400 (2300MHz)、Athlon 4050e (2100MHz)、4450e (2300MHz)、4850e (2500MHz)、5050e (2600MHz) [S1]

## 衍生版本

部分双核产品属 Black Edition 黑盒版本，不锁倍频，现有型号有 90nm F3 步进的 6400+ 及 65nm G2 步进的 5400+、5000+ [S1]。另外，Athlon X2 系列还有 45W 省电版本 BE 系列，以及带 L3 缓存的 Kuma 核心型号 [S1]。

整个 Athlon 64 X2 产品线从2005年持续到2008年，覆盖从低端到高端的双核处理器市场。 [S1]

## 来源

- [S1] AMD Athlon 64 X2 - Wikipedia — https://zh.wikipedia.org/wiki/Athlon_64_X2（抓取日期：2026-07-27）
