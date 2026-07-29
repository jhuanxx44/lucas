---
title: Pentium Pro
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Pentium Pro是英特尔于1995年11月推出的处理器，采用P6微架构，首次集成全速二级缓存并实现双晶粒封装，支持乱序执行。但其缺少MMX指令集且16位性能较差，影响了市场表现。
source_ids:
- S1
---

# Pentium Pro

## 概述

Pentium Pro 是英特尔公司于1995年11月1日推出的第六代x86处理器，开创了Intel的P6处理器架构。该处理器采用Socket 8接口，主频范围为150 MHz至200 MHz，前端总线速度为60至66 MHz，制造工艺为0.35µm至0.50µm。Pentium Pro的P6架构是Intel后期多款CPU的基础，一直沿用至Pentium 4出现之前的所有主流CPU设计，后来的Intel Core多核结构也以P6架构为单核原型。[S1]

## 架构特点

Pentium Pro采用双晶粒封装与内建全速二级缓存的设计，将运算核心与缓冲区两颗芯片一同装入CPU中。片上全速二级缓存使二级缓存可与内核以相同频率运作，为“乱序执行”导致的大量内存查找提供了捷径，直接提升了性能。此外，Pentium Pro具备三个能够把x86指令转换成118位定长的RISC风格微操作的译码器：其中一个能把复杂x86指令转换成4个RISC风格微操作，另外两个解码器各可以把一条“简单”x86指令转换成一条RISC风格微操作，即所谓的“4+1+1”的3路解码格局。Pentium Pro实现了乱序执行（非循序执行的超纯量架构），平均一个周期可执行三个指令，执行速度可达Pentium的2倍。[S1]

## 缓存与内存支持

Pentium Pro的二级缓存容量有256KB、512KB、1MB三款，其中1MB版本使用OLGA（有机塑胶封装）。由于0.35微米制程发热功率甚大，其时脉不曾高于233 MHz（正式版不超频）。Pentium Pro具有64条数据线，可一次传输64位数据；两个8KB的L1 Cache。有36条地址线，定址空间可达64GB。此外，Pentium Pro支持多处理器架构。[S1]

## 性能与缺陷

由于指令队列的问题，Pentium Pro的16位指令执行能力低于Pentium，造成在Windows 3.X、Windows 9X与DOS系统下性能低下，被市场所诟病。同时，为了研发进度、可靠性、成本等综合考虑，所有各型号的Pentium Pro都没有包含MMX指令集，影响了其在图形计算方面的性能。随后的Pentium II改进了上述两个问题。[S1]

## 封装与后续

Pentium Pro以陶瓷或有机塑胶封装推出。其产品化日期为1995年11月1日，生产商为Intel。该处理器奠定了P6微架构的基础，后续的Pentium II、Pentium III等均在此基础上发展。[S1]

## 来源

- [S1] 奔腾Pro - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Pentium_Pro（抓取日期：2026-07-27）
