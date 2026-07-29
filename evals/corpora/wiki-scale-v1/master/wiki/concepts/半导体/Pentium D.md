---
title: Pentium D
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Pentium D是英特尔于2005年推出的双核心处理器系列，基于NetBurst微架构，采用90nm和65nm工艺，包含Smithfield和Presler两种核心，并衍生出支持超线程的Pentium
  Extreme Edition。
source_ids:
- S1
---

# Pentium D

## 概述

**Pentium D** 是英特尔公司的双核心处理器系列之一，于2005年春季的Intel开发者论坛中首度亮相。它把两颗 Pentium 4 Prescott核心放在同一块晶片上。[S1]

| 属性 | 数值 |
| --- | --- |
| 产品化 | 2005至2007 | [S1]
| 生产商 | 英特尔 |
| 微架构 | NetBurst |
| 指令集架构 | MMX, SSE, SSE2, SSE3, x86-64 | [S1]
| 制作工艺/制程 | 90nm 至 65nm | [S1]
| CPU 主频 范围 | 2.66GHz 至 3.73GHz | [S1]
| 前端总线 速率 | 533MT/s 至 1066MT/s | [S1]
| CPU插座 | LGA 775 | [S1]
| 核心代号 | Smithfield, Presler |

## Smithfield核心

Smithfield为英特尔于2005年5月26日推出的第一代双核心处理器核心，以2.8、3.0、3.2GHz运作，各者分别命名为820、830、840。805（2.66GHz, 533MHz外频）则于2006年第一季登场。[S1]

Smithfield采用90奈米技术，两核心各拥有1MB L2内存。各Smithfield核心之Pentium D均不支援超执行绪（Hyper-Threading）（但与Pentium D 800系列之Pentium Extreme Edition则拥有此技术）、Virtualization Technology（VT，前称 Vanderpool）。Smithfield核心之Pentium D均支援英特尔之 EM64T、xD Bit、EIST（820除外），各者皆与主流 Pentium 4 处理器一样，使用LGA 775 Land插槽。除805外，Smithfield处理器均使用800MHz处理器外频，805则是将无法到达FSB800外频的处理器降到FSB533外频，作为低阶的双核心处理器。[S1]

Pentium D处理器起初必须使用以i945/955/975或nVidia nForce 4为北桥的主机板。而i915/925系列的主机板，皆不能使用双核心处理器。不过之后为了进一步抢低价位的市场，i865系列的某些款晶片组在更新BIOS和重新强化电路设计后也可以支援双核心处理器（有些甚至支援到Core 2 Quad系列，但汇流排只能跑FSB800），而其它厂商如VIA、SIS、ATI等也皆有推出一系列相关的晶片组。[S1]

## Presler核心

Presler为英特尔推出的第二代双核心处理器核心，由两颗 Cedar Mill 核心组成，使用65 纳米 技术制成。Presler核心可于各支援Smithfield核心之主机板上使用，并与Smithfield核心一样，使用200MHz（QDR，即800MHz）外频。[S1]

本核心处理器支援VT、EM64T、XD bit及EIST。首批推出的处理器有920、930、940、950、960，频率分别为2.8、3.0、3.2、3.4、3.6GHz。960（3.6GHz, 800MHz外频）于2006年4月30日登场。不支援VT处理器则于2006年7月23日登场，推出的处理器有915、925、935、945，频率分别为2.8、3.0、3.2、3.4GHz。[S1]

## Pentium Extreme Edition

是在2005年春天的开发者论坛中推出的一系列微处理器之品牌名称。这个处理器是以双核心的为基础，但加入超执行绪，因此任何的作业系统会看到四个逻辑核心（2x2实体核心）。这个处理器也支援和。它没有锁频。早期的效能报告提到这个处理器最高能在风冷下以3.8GHz的时钟速度稳定执行。是在2005年早期推出，价格是999.99美元（）或1,200美元（零售）。[S1]

### Smithfield核心（Pentium Extreme Edition）

它是第一代Pentium Extreme Edition所用的核心，跟Penitum D 8XX系列一样，唯一不同的是它有超执行绪技术。这个系列只有一枚处理器：Pentium Extreme Edition 840。这个系列必须使用英特尔的i955X或i975X及NVIDIA的NForce 4 SLI Intel Edition晶片组，使用i945系列晶片组的话会关闭超执行绪功能。[S1]

### Presler核心（Pentium Extreme Edition）

它是第二代Pentium Extreme Edition的核心，跟Pentium 9XX系列一样，但开启了超执行绪技术，使用1066MHz FSB，以及解除了倍频锁。这个系列有两枚处理器，分别是955及965。Presler必须搭配英特尔的i975X晶片组或NVIDIA的nForce4系列。[S1]

## 后继者

英特尔将以使用 Intel Core微处理器架构 的 Intel Core 2 Extreme 取代Pentium Extreme Edition。[S1]

## 来源

- [S1] 奔腾D - Wikipedia — https://zh.wikipedia.org/wiki/Pentium_D（抓取日期：2026-07-27）
