---
title: Opteron
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Opteron是AMD于2003年推出的64位服务器处理器系列，中文名为“皓龙”。采用K8、K10、Bulldozer等微架构，支持x86、x86-64及ARMv8指令集。主要竞争对手为Intel
  Xeon，2017年被Zen架构的EPYC系列取代。
source_ids:
- S1
---

# Opteron

## 概述

**Opteron**（中文名：皓龙）是美国AMD公司于2003年4月22日推出的一系列64位微处理器，主要面向多路服务器领域[S1]。该系列最初采用K8微处理器架构，2007年后逐步过渡至K10架构，最后一代产品基于2011年发布的Bulldozer微架构及其改进版。除x86和x86-64外，Opteron还推出过采用ARM架构（AArch64、ARMv8）的型号[S1]。其主要竞争对手为Intel的Xeon处理器系列。原计划Opteron将改用Zen微架构，但AMD于2017年决定终止该系列，以采用Zen架构的EPYC系列取而代之[S1]。

## 架构与性能

Opteron处理器能以正常速度执行原有32位程序，同时支持新的64位程序，后者可直接访问超过4GB的内存[S1]。处理器集成了内存控制器，访问RAM数据无需通过北桥。在多处理器主板上，Opteron之间通过AMD的HyperTransport技术通信，用户不会察觉一颗Opteron正在访问另一颗Opteron的内存[S1]。首批Opteron型号使用三位数字：第一位代表服务器或工作站的路数（1-way、2-way、4-way、8-way），第二和第三位代表时钟频率。后续Socket F及AM2接口的产品改用四位数字，开头数字越大代表性能越好[S1]。Opteron拥有3至4条HyperTransport线路，而普通Athlon 64与Athlon X2处理器只有1条，在节能技术与热功耗上也有差别[S1]。

## 历史

2007年9月10日，AMD推出首批基于K10微架构、核心代号Barcelona的Opteron 2300及8300系列B2步进处理器，均采用原生四核心设计及65nm SOI制程[S1]。2008年3月1日，AMD出货B3步进Barcelona处理器，解决了B2步进中的TLB Bug；HP、IBM、Dell随即推出采用B3步进的Barcelona处理器的高性能服务器[S1]。2008年3月，在德国CeBIT 2008上，AMD展出代号“Shanghai”（上海）的K10.5核心架构处理器，该处理器改进了IPC（每时钟周期指令）并将L3缓存增大至6MB[S1]。2008年5月25日，IBM为美国国家核能安全管理部（NNSA）打造超级计算机“走鹃”（Roadrunner），使用6192颗AMD Opteron处理器与12960颗PowerX Cell 8i处理器，计算峰值达1.026 petaFLOPS，2008年位居世界500强超级计算机首位[S1]。2008年7月25日，AMD计划推出12核心Opteron处理器，并升级至Socket G34插槽搭配Maranello服务器平台；12核心Opteron预计2010年面世，支持DDR3内存与4路HyperTransport 3.0协议，将采用45nm制程的12核心Magny Cours和6核心Sao Paulo[S1]。2008年7月28日，中国中央电视台引进1000多台搭载AMD Opteron四核心的双路服务器，用于北京奥运赛事直播[S1]。2008年7月29日，AMD Opteron四核处理器在双路、四路服务器上创造SPEC Web2005两项世界纪录：HP ProLiant DL385 G5（双路Opteron 2356 2.3 GHz）得分30007，HP ProLiant DL585 G5（四路Opteron 8356 2.3 GHz）得分43854[S1]。2008年8月11日，搭载Opteron四核2360 SE的HP ProLiant DL785 G5在TPC-H@300 GB决策支持测试中打破世界纪录，并在SAP销售和分销标准应用测试中获同类第一[S1]。AMD 45nm Opteron提前至2008年10月上市，同时推出服务器芯片组AMD SR5600；45nm Opteron将推出9种型号，频率2.3GHz至2.7GHz，采用Socket F接口、6MB L2缓存、TDP 75W，HyperTransport仍为2.0版本[S1]。

## 产品与代际

Opteron系列覆盖从130nm到32nm的多种制造工艺，CPU主频范围为1.4GHz至3.5GHz，支持的插座包括Socket 939、940、AM2/AM2+、F/F+、AM3/AM3+、C32、G34等[S1]。核心代号众多，K8时代的SledgeHammer、Venus、Troy、Athens、Denmark、Italy、Egypt、Santa Ana、Santa Rosa；K10时代的Barcelona、Budapest、Shanghai、Istanbul、Lisbon、Magny Cours；Bulldozer及Piledriver时代的Valencia、Interlagos、Zurich、Abu Dhabi、Warsaw、Delhi、Seoul[S1]。

## 竞争与后续

Opteron的主要竞争对手是Intel Xeon系列。2017年，AMD决定终止该系列，以采用Zen微架构的EPYC系列取代之[S1]。

## 另见

- AMD Opteron处理器列表
- AMD处理器列表
- x86-64 [S1]
- AMD
- AMD EPYC

## 来源

- [S1] Opteron - Wikipedia — https://zh.wikipedia.org/wiki/Opteron（抓取日期：2026-07-27）
