---
title: Sempron
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Sempron是AMD的入门级微处理器，中文名“闪龙”，2004年至2014年间生产，用于取代Duron并与Intel Celeron竞争。涵盖多代核心，包括Socket
  A、754、939、AM2、AM3和AM1，拥有从单核到双核、APU的演进路线。
source_ids:
- S1
---

# Sempron

## 概述

**Sempron** 是美国 AMD 公司的入门级微处理器，中文官方名称为「闪龙」，用以取代 Duron 处理器及与英特尔公司的 Celeron 和 Celeron D 处理器竞争。名字“Sempron”来自拉丁文的“semper”，意即「每天」，代表Sempron为每日的运算之选。[S1]

## 开发历程及功能

第一代Sempron处理器采用 Athlon XP 的“Thoroughbred”及“Thorton”内核，使用 Socket A 插座，拥有256KB第二层快取及166 MHz FSB（FSB 333）。最后一款使用 Socket A 的3000+则使用Barton内核，拥有512KB第二层快取。从硬件及用家的角度来看，Socket A(462)的Sempron算是Athlon XP的更名。现时所有Socket A的Sempron处理器已经停产。[S1]

第二代Sempron处理器使用 Athlon 64 的“Paris”及“Palermo”内核，以及 Socket 754 插座，其第二层快取仅提供128KB和256KB。这些Sempron与Athlon 64拥有不少共通点，包括集成记忆体控制器、 HyperTransport 汇流排及 NX位元，但早期的K8 Sempron不支援 AMD64。第一款使用Socket 754的Sempron是3100+，然后是稍慢的2600+和2800+。[S1]

自Intel把 EM64T 加进Celeron处理器后，AMD也于2005年6月推出64位元的Sempron，支援NX防毒功能，但不支援Dual DDR记忆体。型号方面，分别有2500+、2600+、2800+、3000+、3100+和3300+。这些处理器被用家称为“Sempron 64”，但并非官方名称。[S1]

2006年，AMD推出 Socket AM2 版本的Sempron处理器，其功能与之前的版本相同，但支援 DDR2 SDRAM 记忆体控制器。普通版本的 TDP功耗值为62 W，低功耗小型化版本则为35 W。[S1]

2008年，AMD推出双核版本的Sempron处理器，首款产品型号为2100+，时脉1800MHz，TDP功耗值为65w。[S1]

2014年，AMD推出首款 Sempron APU，使用 Kabini 核心。以廉价及低功耗市场作为定位，具有双核心和四核心两个系列、全部均是28nm制程及25W热设计功耗，全部Sempron APU整合 AMD Radeon R3 图形处理器、北桥及南桥，使用全新 Socket AM1 CPU 插座。[S1]

## Socket A型号

### Thoroughbred B/Thorton核心 (130 nm)
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：256 KB，全速 [S1]
- MMX， 3DNow!， SSE [S1]
- Socket A (EV6) [S1]
- FSB：166 MHz (FSB 333) [S1]
- VCore: 1.60 V [S1]
- 推出日期：2004年7月28日 [S1]
- 时脉：1500 MHz - 2000 MHz (2200+ 至 2800+)[S1]

### Barton核心 (130 nm)
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：512 KB，全速 [S1]
- MMX， 3DNow!， SSE [S1]
- Socket A (EV6) [S1]
- FSB：166 MHz (FSB 333) - 200 MHz (FSB 400) [S1]
- VCore: 1.6 - 1.65 V [S1]
- 推出日期：2004年9月17日 [S1]
- 时脉：2000 - 2200 MHz (3000+ 和 3300+)[来源请求][S1]

## Socket 754型号

### Paris核心 (130 nm SOI)
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：128/256 KB，全速 [S1]
- MMX， 3DNow!， SSE， SSE2 [S1]
- 整合记忆体控制器
- Socket 754，800 MHz HyperTransport [S1]
- VCore: 1.40 V [S1]
- 推出日期：2004年7月28日 [S1]
- 时脉：1800 MHz (3000+ 和 3100+)[S1]

### Palermo核心 (90 nm SOI)
- Early models are downlabeled "Oakville" mobile Athlon64 [S1]
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：128/256 KB，全速 [S1]
- MMX， 3DNow!， SSE， SSE2， SSE3 [S1]
- Sempron 3000+ 或更高型号支援 Cool'n'Quiet [S1]
- 由步进 E6 开始支援 AMD64 [S1]
- 加强防毒功能（ NX bit）
- 整合记忆体控制器
- Socket 754，800 MHz HyperTransport [S1]
- VCore: 1.40 V [S1]
- 推出日期：2005年2月 [S1]
- 时脉：1400 - 2000 MHz [S1]
  - 128 KB L2快取：1600 - 2000 MHz (2600+ 至 3300+) [S1]
  - 256 KB L2快取：1400 - 2000 MHz (2500+ 至 3400+) [S1]
- 步进： **D0** (Part No.: *BA), **E3** (Part No.: *BO), **E6** (Part No.: *BX)[S1]

## Socket 939型号[来源请求]

### Palermo核心 (90 nm SOI)
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：128/256 KB，全速 [S1]
- MMX， 3DNow!， SSE， SSE2， SSE3， AMD64（只限步进E6）, Cool'n'Quiet， NX bit [S1]
- 整合记忆体控制器
- Socket 939，800 MHz HyperTransport [S1]
- VCore: 1.35/1.4 V [S1]
- 推出日期：2005年10月 [S1]
- 时脉：1800 - 2000 MHz [S1]
  - 128 KB L2快取（3000+ 和 3400+） [S1]
  - 256 KB L2快取（3200+ 和 3500+） [S1]
- 步进： **E3** (Part No.: *BP), **E6** (Part No.: *BW)[S1]

## Socket AM2型号

### Manila核心 (90 nm SOI)
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：128/256 KB，全速 [S1]
- MMX， 3DNow!， SSE， SSE2， SSE3， AMD64， NX bit [S1]
- Sempron 3200+ 或更高型号支援 Cool'n'Quiet [S1]
- 整合128-bit（双通道） DDR2 记忆体控制器 [S1]
- Socket AM2, 800 MHz HyperTransport [S1]
- VCore: 1.25 - 1.4 V (Energy Efficient SFF 版本为 1.20 - 1.25V) [S1]
- 推出日期：2006年5月23日 [S1]
- 时脉：1600 - 2200 MHz [S1]
  - 128 KB L2快取：1600 - 2000 MHz (2800+ 至 3500+) [S1]
  - 256 KB L2快取：1600 - 2200 MHz (3000+ 至 3800+) [S1]
- 步进： **F2** (Part No.: *CN, *CW)[S1]

### Sparta核心 (65 nm SOI)
- L1快取：64 + 64 KB（数据 + 指令） [S1]
- L2快取：256 KB，全速 [S1]
- MMX， 3DNow!， SSE， SSE2， SSE3， AMD64， NX bit， Cool'n'Quiet [S1]
- 整合128-bit（双通道） DDR2 记忆体控制器 [S1]
- Socket AM2，800 MHz HyperTransport [S1]
- VCore: 1.20/1.40 V [S1]
- 推出日期：2007年8月20日 [S1]
- 时脉：1900 - 2300 MHz [S1]
  - 256 KB L2快取：1900 - 2000 MHz (LE-1100 至 LE-1150) [S1]
  - 512 KB L2快取：2200 - 2300 MHz (LE-1250 至 LE-1300) [S1]
- 步进： **G1**、 **G2** (Part No.: *DE, *DP)[S1]

### Sherman核心 (65 nm SOI)
- L1快取：64KB x 2 + 64KB x 2（数据 + 指令） [S1]
- L2快取：256KB x 2，全速 [S1]
- MMX， 3DNow!， SSE， SSE2， SSE3， AMD64， NX bit， Cool'n'Quiet [S1]
- 整合128-bit（双通道） DDR2 记忆体控制器 [S1]
- Socket AM2，800 MHz HyperTransport [S1]
- VCore: 1.30 V [S1]
- 推出日期：2008年2月19日 [S1]
- 时脉：1800 - 2200 Mhz [S1]
  - 256 KB x 2 L2快取：1800 MHz (Sempron X2-2100+) (SDO2100IAA4DO) [S1]
  - 256 KB x 2 L2快取：2000 MHz (Semrpon X2-2200+) (SDO2200IAA4DO) [S1]
  - 256 KB x 2 L2快取：2200 MHz (Sempron X2-2300+) (SDO2300IAA4DO) [S1]
- 步进： **G2**[S1]

## Socket AM3型号

### Sargas核心 (45 nm SOI)
- L1快取:64 + 64 KB（数据 + 指令） [S1]
- L2快取:1024 KB，全速 [S1]
- MMX， 3DNow!， SSE， SSE2， SSE3， SSE4a， AMD64， NX bit [S1]
- 支援 Cool'n'Quiet
- 时脉：2700 MHz [S1]
- 功耗：45 W[S1]

### Regor核心 (45 nm SOI)
- L1快取: 64 + 64 KB (数据 + 指令） [S1]
- L2快取:1024 KB,全速 [S1]
- MMX, 3DNow!, SSE, SSE2, SSE3, SSE4a, AMD64, AMD-V [S1]
- 支持 Cool'n'Quiet
- 时脉：2400-2500 MHz [S1]
- 功耗：45 W[S1]

## Socket AM1型号

### Kabini核心 (28 nm SOI)
- 双核心系列:
  - L1快取:64 + 64 KB（数据 + 指令） [S1]
  - L2快取:1024 KB，全速 [S1]
  - MMX， SSE， SSE2， SSE3， SSSE3， SSE4.1， SSE4.2， SSE4A， AMD64， AMD-V， AES， AVX [S1]
  - 支援 Cool'n'Quiet
  - 时脉：1450 MHz [S1]
  - 整合 AMD Radeon R3 图形处理器 (8个CU单元共128个流处理器, 时脉：400 MHz) [S1]
  - 功耗：25 W[S1]

- 四核心系列:
  - L1快取:128 + 128 KB（数据 + 指令） [S1]
  - L2快取:2048 KB，全速 [S1]
  - MMX， SSE， SSE2， SSE3， SSSE3， SSE4.1， SSE4.2， SSE4A， AMD64， AMD-V， AES， AVX [S1]
  - 支援 Cool'n'Quiet
  - 时脉：1300 MHz [S1]
  - 整合 AMD Radeon R3 图形处理器 (8个CU单元共128个流处理器, 时脉：450 MHz) [S1]
  - 功耗：25 W[S1]

## 来源

- [S1] AMD Sempron - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Sempron（抓取日期：2026-07-27）
