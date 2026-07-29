---
title: Athlon 64
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Athlon 64是AMD于2003至2009年生产的64位微处理器，采用K8微架构，支持AMD64指令集，提供Cool'n'Quiet节能技术和HyperTransport总线。产品分64、FX及X2三个版本，使用Socket
  754/939/940/AM2/AM2+等插座，内置内存控制器，涵盖单双核心，主频1.0-3.2 GHz。
source_ids:
- S1
---

# Athlon 64

## 概述

**Athlon 64** 是美国 AMD 公司的64位 微处理器 型号之一，它支援 AMD64 架构，用于针对个人客户的64位处理器市场。早期AMD K8开发计划中，K8代号为 **Hammer**，并使用与 IBM 共同开发的 **SOI**（绝缘上覆矽）技术。[S1]

**Athlon 64** 分为 64、 FX 及 X2 三个版本，当中以Athlon 64-FX的效能为最高，与 Opteron 相似。Athlon 64除支援AMD64外，还兼容16位和32位的 x86 平台。[S1]

此外，Athlon 64有一种名为 Cool'n'Quiet 的技术，当用户执行一些对处理器负荷较少的程式时，处理器的速度和电压相应降低，从而达到省电的效果。[S1]

**Athlon 64** 使用 **HyperTransport** 总线技术，从而提高效能。[S1]

## 规格与插座

Athlon 64 处理器产品化时间为2003至2009年，微架构为AMD K8，指令集架构包括MMX、SSE、SSE2、SSE3、AMD64、3DNow!，仅部分型号支援AMD-V。制作工艺从0.13µm至65nm，核心数量1至2个，CPU主频范围1.0GHz至3.2GHz，HyperTransport速率800MT/s至1000MT/s。CPU插座包括Socket 754、Socket 939、Socket 940、Socket AM2、Socket AM2+。[S1]

Socket754的 **Athlon 64** 大多为ClawHammer核心，封装为mPGA。内置单通道DDR400内存控制器。[S1]

Socket939的 **Athlon 64** 大多为Winchester核心，封装为mPGA。功耗较ClawHammer核心小。内置双通道DDR400内存控制器。[S1]

Socket940的FX－51为SledgeHammer核心；FX－53、FX－55为ClawHammer核心；FX-57则为San Diego核心。封装为CuPGA。内置双通道DDR400内存控制器。支持ECC校检。[S1]

在A64于2003年9月问世时，仅S754及S940（Opteron用）两款插座可供用家选择，而当时的记忆体控制器，在A64刚推出时并未支援在双通道状态下，执行未经缓冲的记忆体，S754版的A64在这个时候推出，正好弥补了这个不足。另外，AMD也推出非多处理器版本的Opteron，称为Athlon 64 FX，它使用S940插座，其倍频没有锁定，特别为爱好 超频 的高阶用者而设计，与Intel的Pentium 4 Extreme Edition竞争。[S1]

2004年6月，AMD推出S939插座，给新型号的A64使用，并把S754降格给较慢的A64及Sempron，以取代Socket A，而S940则供伺服器用的Opteron使用。S939支援双通道记忆体。[S1]

2006年5月，AMD发行Socket AM2版本的处理器，这款插座支持 DDR2 记忆体。[S1]

2008年，AMD发行Socket AM2+版本的处理器，这款插座支援 Phenom 处理器和HyperTransport 3.0协定。[S1]

## 核心列表

### ClawHammer (130 nm SOI)
- 处理器步进：C0, CG [S1]
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：1024 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， AMD64， Cool'n'Quiet， NX Bit (only **CG**) [S1]
- 插座：Socket 754，800 MHz HyperTransport (HT800)；Socket 939，1000 MHz HyperTransport (HT1000) [S1]
- 核心电压 VCore: 1.50 V [S1]
- 功耗 (TDP)：最大 89 W [S1]
- 首次发表：2003年9月23日 [S1]
- 时脉：2000 - 2600 MHz [S1]

### Newcastle (130 nm SOI)
- 处理器步进：CG
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：512 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， AMD64， Cool'n'Quiet， NX Bit (only **CG**) [S1]
- 插座：Socket 754，800 MHz HyperTransport (HT800)；Socket 939，1000 MHz HyperTransport (HT1000) [S1]
- 核心电压 VCore: 1.50 V [S1]
- 功耗 (TDP)：最大 89 W [S1]
- 首次发表：2004年 [S1]
- 时脉：1800 - 2400 MHz [S1]

### Winchester (90 nm SOI)
- 处理器步进：D0 [S1]
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：512 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， AMD64， Cool'n'Quiet， NX Bit [S1]
- 插座： Socket 939，1000 MHz HyperTransport (HT1000) [S1]
- 核心电压 VCore: 1.40 V [S1]
- 功耗 (TDP)：最大 67 W [S1]
- 首次发表：2004年 [S1]
- 时脉：1800 - 2200 MHz [S1]

### Venice (90 nm SOI)
- 处理器步进：E3, E6 [S1]
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：512 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， SSE3， AMD64， Cool'n'Quiet， NX Bit [S1]
- 插座：Socket 754, 800 MHz HyperTransport (HT800)；Socket 939，1000 MHz HyperTransport (HT1000) [S1]
- 核心电压 VCore: 1.35 / 1.40 V [S1]
- 功耗 (TDP)：最大 67 W [S1]
- 首次发表：2005年4月4日 [S1]
- 时脉：1800 - 2400 MHz [S1]

### San Diego (90 nm SOI)
- 处理器步进：E4, E6 [S1]
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：1024 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， SSE3， AMD64， Cool'n'Quiet， NX Bit [S1]
- 插座： Socket 939，1000 MHz HyperTransport (HT1000) [S1]
- 核心电压 VCore: 1.35 / 1.40 V [S1]
- 功耗 (TDP)：最大 67 W [S1]
- 首次发表：2005年4月15日 [S1]
- 时脉：2200 - 2800 MHz [S1]

### Orleans (90 nm SOI)
- 处理器步进：F2, F3 [S1]
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：512 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， SSE3， AMD64， Cool'n'Quiet， NX Bit， Pacifica [S1]
- 插座： Socket AM2，2000 MHz HyperTransport (HT2000) [S1]
- 核心电压 VCore: 1.20 / 1.25 / 1.35 / 1.40 V [S1]
- 功耗 (TDP)：最大 62 W 最少 35 W [S1]
- 首次发表：2006年5月23日 [S1]
- 时脉：1800 - 2600 MHz [S1]

### Lima (65 nm SOI)
- 处理器步进：G1、G2 [S1]
- 一级缓存：64 + 64 KB [S1]
- 二级缓存：512 KB，全速 [S1]
- 指令集： MMX，Extended 3DNow!， SSE， SSE2， SSE3， AMD64， Cool'n'Quiet， NX Bit， AMD Virtualization [S1]
- 插座： Socket AM2，2000 MHz HyperTransport (HT2000) [S1]
- 核心电压 VCore: 0.8 / 1.25 / 1.35 / 1.40 V [S1]
- 功耗 (TDP)：最大 45 W [S1]
- 首次发表：2007年2月20日 [S1]
- 时脉：1000 - 2400 MHz [S1]

## 来源

- [S1] AMD Athlon 64 - Wikipedia — https://zh.wikipedia.org/wiki/Athlon_64（抓取日期：2026-07-27）
