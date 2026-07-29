---
title: Pentium 4
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Pentium 4 是 Intel 于 2000 年推出的第七代 x86 微处理器，采用 NetBurst 架构，主打高时钟频率，最高达 3.8
  GHz。该系列包括 Willamette、Northwood、Prescott 等核心，但最终因功耗过高而被放弃，转向 Core 微架构。
source_ids:
- S1
---

# Pentium 4

## 概述

Pentium 4（简称 P4 或奔4）是 Intel 生产的第七代 x86 微处理器，采用 NetBurst 架构，于 2000 年 11 月发布 [S1]。它是继 1995 年的 P6 架构 Pentium Pro 之后首款全新设计的处理器 [S1]。产品化时间为 2000 至 2006 年，采用 180nm 至 65nm 制程，CPU 主频范围 1.3 GHz 至 3.8 GHz，前端总线速率 400 MHz 至 1066 MHz [S1]。Pentium 4 的设计目标是适应更快的时钟速度，通过超长流水线实现高频率，但牺牲了每周期性能 [S1]。英特尔曾宣称 NetBurst 架构能运行在 10 GHz，但实际在 3.8 GHz 便遇到无法解决的高功耗问题，最终于 2005 年中放弃 NetBurst，转向 Core 微架构 [S1]。

## 核心演变

### Willamette

首款 Pentium 4 核心代号为 Willamette，使用 180nm 制程，主频 1.4 GHz 或 1.5 GHz，搭配 Socket 423 插座 [S1]。它采用 400 MHz 前端总线（实际为 100 MHz 四倍数据速率），集成 256 KB L2 缓存 [S1]。性能测试中表现不佳，多数情况下不及 AMD Athlon 或高频 Pentium III [S1]。尽管售价高昂（819 美元/千颗），销售仍因需搭配昂贵的 RDRAM 而受限 [S1]。2001 年 7 月后，Intel 推出 1.6 至 2.0 GHz 版本，并发布支持 PC133 SDRAM 的 i845 芯片组，大幅提升销量 [S1]。

### Northwood

2002 年 1 月，Intel 发布 Northwood 核心，使用 130nm 制程，L2 缓存增至 512 KB [S1]。初期仅支持 Socket 478，但可通过转接卡用于旧 Socket 423 主板 [S1]。Northwood 核心带来了 533 MHz 前端总线（2002 年 5 月）和 800 MHz 前端总线（2003 年 4 月）版本，后者全系支持超线程技术 [S1]。最高型号为 3.4 GHz（2004 年初）[S1]。Northwood 被认为是 Pentium 4 时代最具竞争力的核心，但也存在“突然死亡症”——电压超过 1.7V 时因电子迁移导致芯片永久损坏 [S1]。此外，基于 Northwood 的移动版包括 Mobile Pentium 4-M（2002 年 4 月发布，无超线程）和 Mobile Pentium 4（支持超线程与 EIST，FSB 533 MHz，90nm 制程最高 3.46 GHz）[S1]。

### Prescott

2004 年 2 月发布 Prescott 核心，采用 90nm 制程，L2 缓存增至 1 MB，流水线加深至 31 级 [S1]。Prescott 支持 SSE3 指令集，并首次引入 XD bit（执行禁止位）和 EM64T（64 位扩展）[S1]。但功耗大幅上升，同频下比 Northwood 多产生约 60% 热量，插座从 Socket 478 转为 LGA775 后功耗进一步增加 [S1]。性能测试显示 Prescott 在游戏应用中略慢于 Northwood，仅在多线程媒体应用中占优 [S1]。最高主频达 3.8 GHz（型号 570J/571），但因功耗问题无法突破 4 GHz [S1]。英特尔曾计划开发 Prescott 2M（L2 缓存 2 MB，6xx 系列，2005 年发布），最终于 2006 年 1 月推出 65nm 的 Cedar Mill 核心（L2 2 MB，TDP 86W），仍未能扭转局面 [S1]。

### 双核心 Pentium D

双核心版本基于 Smithfield（90nm，2005 年 5 月）和 Presler（65nm，2006 年第一季度）核心，市场名称为 Pentium D [S1]。Smithfield 由两个 Prescott 核心组成，功耗约 155W，主流型号 8xx 系列 [S1]。Presler 核心的 Pentium D 型号包括 920 至 950，最高主频 3.73 GHz（极致版 965）[S1]。

### Extreme Edition

2003 年 9 月发布 Pentium 4 Extreme Edition（P4EE），基于 Gallatin 核心（130nm），增加 2 MB L3 缓存，源自 Xeon MP [S1]。初期使用 Socket 478 和 800 MHz 前端总线，后期推出 LGA775 版本和 1066 MHz 前端总线版本（如 3.46 GHz）[S1]。最后一款基于 Prescott 2M 的 3.73 GHz 极致版实际性能反而不如 3.46 GHz 版本 [S1]。

## 技术特点

Pentium 4 全系列采用 NetBurst 微架构，特点是超长流水线（20 或 31 级）、快速执行引擎（ALU 以双倍核心频率运行）、SSE/SSE2/SSE3 指令集支持 [S1]。前端总线采用四倍数据速率（QDR），实际时钟频率为标称值的四分之一 [S1]。不同核心的缓存配置各异：Willamette 和早期 Northwood 的 L1 数据缓存为 8 KB，Prescott 起增至 16 KB [S1]。技术特性包括超线程（从 Northwood 3.06 GHz 开始部分支持）、EM64T（Prescott F 系列起）、XD bit（Prescott 5x0J 系列起）、EIST（SpeedStep，移动版和部分桌面版）以及虚拟化技术（Prescott 2M 6x2 系列）[S1]。

## 评价与失败

Pentium 4 是市场驱动技术的典型案例：为迎合消费者对高时钟频率的偏好，牺牲每周期性能以追求极高频率 [S1]。这导致其整数和浮点处理能力相对前代 P6 架构不升反降 [S1]。AMD 采用 PR 值标称 Athlon XP 与之对应 [S1]。随着频率攀升，功耗与发热急剧恶化，最终在 3.8 GHz 附近达到瓶颈，迫使英特尔放弃 NetBurst 架构，转向基于 Pentium M 的 Core 微架构 [S1]。分析人士认为，Pentium 4 的研发实质上是以失败告终，其所谓的 10 GHz 远景从未实现 [S1]。

## 来源

- [S1] 奔腾4 - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Pentium_4（抓取日期：2026-07-27）
