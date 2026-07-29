---
title: Pentium III
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: Pentium III 是英特尔于1999年推出的x86微处理器，采用P6微架构，支持SSE指令集。主要核心包括Katmai、Coppermine、Coppermine-T和Tualatin，产品化至2003年。曾因处理器序列号引发隐私争议。
source_ids:
- S1
---

# Pentium III

## 概述

**Pentium III** 是 英特尔 的 x86-P6架构之 微处理器，于1999年2月底推出 [S1]。刚推出的版本与早期的 Pentium II 非常相似，最值得注意的不同是 SSE 指令的扩充，以及在每个晶片制造的过程加入有争议的序号进去 [S1]。与Pentium II相同，也有低阶的 Celeron 版本和高阶的 Xeon 版本 [S1]。Pentium III最后被 Pentium 4 所取代，Pentium III的改进设计就是后来的 Pentium M [S1]。产品化期间为1999年至2003年，生产商为英特尔，微架构为P6，指令集架构为x86 (686)，制作工艺从0.25µm至0.13µm，CPU主频范围450 MHz至1.4 GHz，前端汇流排速率100 MHz至133 MHz，CPU插座包括Slot 1和Socket 370 [S1]。核心代号有Katmai、Coppermine、Coppermine-T、Tualatin [S1]。

## Pentium III核心

### Katmai

Katmai是Pentium III的首发型号，与Pentium II非常相似（均使用0.25µm制程，工作电压2.0V，部分早期产品的卡匣仍然刻有Pentium II字样），差别是加入SSE指令集，以及改进的，比Pentium II拥有较好效能的第一级快取(L1) [S1]。首次推出的速度是450和500MHz [S1]。另外两个版本是：550 MHz于1999年5月17日，600MHz于1999年8月2日推出，工作电压提高至2.05V [S1]。在1999年9月27日，推出533B和600B的版本，B型指133MHz前端汇流排，而先前的是100MHz [S1]。Katmai使用与 Pentium II 相同的插座介面 - Slot 1，特征是卡匣式的CPU组件（称为SECC2），安装方式类似于扩展卡 [S1]。L2为板载的分立晶片，与CPU的连接形式类似于显示卡的显存 [S1]。512KB板载L2只能工作在CPU主频的一半，亦有一定的延迟，这限制了Katmai的效能 [S1]。零售的Katmai预装了带有定速高速风扇的卡匣（使用倒扣式卯榫固定，通常需要损伤性拆除），散热更换比较困难 [S1]。供给OEM厂商的版本可能只含PCB，由OEM自行寻第三方厂家生产配套散热系统，这种设计的风扇可能不在卡匣上而利用系统整体的风道散热，往往能提供更低的噪音，但牺牲了互换性 [S1]。

### Coppermine

Intel重作晶片内部的设计，制成了第二个版本Coppermine [S1]。Coppermine于1999年10月25日推出，使用0.18µm制程制造，工作电压下降到1.65V至1.75V [S1]。最大的改善是L2整合于CPU之内（称为片载），实现了全速（同步于CPU主频）和更低的延迟，第二级快取容量虽然减少了一半（256 KB，相对于Katmai的512KB)，但比Katmai于效能上很大进步 [S1]。同频之下处理指令的效能平均增加了30% [S1]。全速片载L2最初应用于1997年上市的 Pentium Pro，在当时是供应专业市场的高端产品，而Coppermine的定位是普及市场 [S1]。大多数的Coppermine恢复了插槽式安装(370针脚，称为PGA 370)，为了兼容早些年发布的主机板，也有电气规格完全相同的Slot 1版本 [S1]。较旧的主机板如果获得厂家支持，有可能通过更新BIOS的方式支持Coppermine，前提是CPU供电的硬体部分兼容VRM 8.4规格 [S1]。PGA 370版本外观上看是裸晶直接置于基板之上(这种构造最早被应用于移动CPU - 移动版Pentium 2)，并使用扣具式散热器直接卡在塑胶制的插槽上，由于一些扣具本身的设计不良，安装人员经验不足等问题，不当的装卸可能造成CPU或固定座永久的物理损坏，而这种损坏属于人为，并不在保修范围内 [S1]。PGA 370版本的Coppermine亦是Intel到目前最后一款用于桌面的裸晶处理器 [S1]。1.13GHz的版本于2000年中期推出(步进为Stepping cC0)，但是很快证明这款CPU在很多情况下运行不稳定，因而召回 [S1]。研究证明这个问题是由于片载快取无法在1GHz以上的速度运作 [S1]。此版本被民间俗称为“矿渣”（因Coppermine中文被翻译为“铜矿”）英特尔花费至少6个月来解决这个问题，于2001年才推出稳定的1.1和1.13GHz版本(Stepping cD0，运行电压提升到1.75V) [S1]。

### Coppermine-T

FC-PGA2封装的Coppermine CPU [S1]。加入了一体式散热器(IHS)亦起到保护盖的作用，防止装卸散热器过程中对晶体的损坏 [S1]。电气性能与Coppermine有小的差异，区别在于AGTL信号电压降低，但这对使用性能并无影响，新的信号电压标准沿用到后续产品Tualatin上 [S1]。Coppermine-T发售量较少，需要订货时专门备注 [S1]。必须使用新设计的平底散热器以配合 [S1]。

### Tualatin

第三个版本Tualatin采用了当时最新的0.13um制程，因而能以更小的核心面积，实现更高的主频和容纳更大的缓存 [S1]。Intel把512KB的Tualatin命名为为Pentium III-S [S1]。Pentium III-S主要是供给 刀锋伺服器 厂家，不面向零售渠道供货，主要是担心内部竞争，影响自家高阶产品Pentium 4的销售 [S1]。事实上，家用主机板（Intel 815E或者VIA 694T芯片组）硬件上完全可以支持单颗Pentium III-S完全发挥 [S1]。也就是说爱好者只要有渠道获得P3-S芯片，就可以组装出当时性价比很高的个人电脑 [S1]。面向个人用户的Tualatin Pentium III则继承了Coppermine的256K L2，若不计低压带来功耗方面的优势，和Coppermine相较就是主频较高 [S1]。移动版本的Pentium III-m Tualatin也配备了和Pentium III-s相同的512KB缓存，最高主频则达到1.33GHz [S1]。这种芯片需配合专门的830MP移动芯片组运行 [S1]。Tualatin不再有官方的Slot 1版本 [S1]。不过当时有第三方厂家的转接器，比如台湾产的PowerLeap，可以让旧型的主机板（包括早至1998年的440BX）升级至Tualatin平台 [S1]。因为Tualatin的工作电压和信号电压低于老式主板能提供的最低限，转接器要点是通过电路实现主动降压 [S1]。512KB L2快取的Tualatin性能在很多测试项目中都可以超过同频，甚至主频更高的Willamette核心奔腾4 [S1]。单就运算能力而言，P3-S 1.4GHz在一些项目测试中可以媲美Willamette 2.0GHz，然而总体平台性能往往仍然是P4平台胜出，特别是较复杂的3D设计，游戏等应用 [S1]。这主要是因为Tualatin的内存界面并没有采用奔腾4的四倍速前端总线（Quad FSB），因而只能支持老式的PC 133 SDRAM，也限制AGP 4X与CPU的交信速度，这限制了总体效能，包括图形效能 [S1]。Pentium III Tualatin是在2001年至2002年早期之间所推出，速度分别为1.0、1.13、1.2、1.26、1.33和1.4 GHz，不提供更高主频据信主要是市场考虑而不是技术限制 [S1]。超频测试早已证明体质较好的Tualatin个体可以稳定工作在1.7G左右，后来 Pentium M 更是官方证明了0.13 μm制程不但能让类似架构在1.73GHz稳定运行，也可以接入QFSB总线 [S1]。Tualatin核心是以 俄勒冈 地区的图拉丁谷（英语：Tualatin Valley）和图拉丁河（英语：Tualatin River）来命名 [S1]。

## 序号争议

“处理器序列号”(Processor Serial Number (PSN))是作为Pentium III的一项技术功能加入的，这是一种制造时烧录进去的独特序号，可以通过CPUID指令在BIOS环境和操作系统中进行提取 [S1]。其实不仅是CPU，很多数字设备很早就有类似的功能，即可以通过SPI等较原始的通信方式获取储存在ROM中的唯一标号作为硬件识别 [S1]。但Pentium III的应用对于CPU这种硬件是史上第一次，而且由于是制造时硬件一次性写入，基本没有篡改的可能 [S1]。然而在对数据隐私重视起步较早的欧盟，这项技术很快引起了争议 [S1]。欧洲议会的科技附件测试委员会（STOA, Science and Technology Options Assessment)在99年11月根据此前的报告，提议有关部门对Intel的CPU序号技术采取法律措施，并建议欧盟计算机用户停止装置带有PSN的处理器 [S1]。理由是用户的计算机信息可能被无授权的滥用，比如用于跟踪定位，或监视计算机配件的物理流向等 [S1]。最终这一问题没有正式立案，但Intel在Pentium III Tualatin发售时悄然的撤销了这项技术 [S1]。

## 来源

- [S1] 奔腾III - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Pentium_III（抓取日期：2026-07-27）
