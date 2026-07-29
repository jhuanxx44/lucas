---
title: PowerPC
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: PowerPC是由Apple、IBM、Motorola组成的AIM联盟于1991年开发的RISC指令集架构，基于IBM POWER架构，具有可伸缩性好、灵活的特点。1993年推出首款处理器PowerPC
  601，曾用于苹果Macintosh、任天堂GameCube/Wii/Wii U、微软Xbox 360和索尼PlayStation 3等产品。2005年后苹果转向Intel
  x86，但PowerPC仍用于嵌入式等领域。[S1]
source_ids:
- S1
---

# PowerPC

## 历史

PowerPC（Performance Optimization With Enhanced RISC – Performance Computing，有时简称PPC）是一种精简指令集（RISC）的指令集架构ISA，其基本设计源自IBM的POWER架构。[S1]

1991年，Apple、IBM、Motorola组成AIM联盟，意欲发展一泛用的微处理器架构，其成果即为PowerPC。[S1] PowerPC架构基础来自于1990年随RISC System/6000推出的IBM POWER架构，而POWER架构又是从早期的RISC架构（比如IBM 801）与MIPS架构的处理器得到灵感的。[S1] PowerPC架构的特点是可伸缩性好、方便灵活。[S1] 第一代PowerPC采用0.6微米制程，晶体管约为单芯片280万个。[S1]

以PowerPC架构发展出来的第一个芯片是1993年推出的PowerPC 601，而IBM以PowerPC 601推出了RS/6000 POWERstation 250工作站，苹果电脑则推出第一代的PowerMacintosh。[S1]

1998年，铜芯片问世。[S1] 2000年，IBM开始大批推出采用铜芯片的产品，如RS/6000的X80系列产品。[S1] 铜制程取代了已经沿用了30年的铝制程，使硅芯片多CPU的生产工艺达到了0.2微米的水平，单芯片整合了2亿个晶体管，大大提高了运算性能；而1.8V的低电压操作（原为2.5V）大大降低了芯片的耗能，容易散热，从而大大提高了系统的稳定性。[S1]

但除了苹果公司的麦金塔电脑以外，使用PowerPC处理器的个人电脑很少，而自2005年起，麦金塔也转用Intel x86。[S1]

## PowerPC处理器

### PowerPC 601至PowerPC 603e

| 型号 | 601 | 601v | 602 | 603 | 603e | 604 | [S1]
| --- | --- | --- | --- | --- | --- | --- |
| 时钟（MHz） | 50至80 | 100 | 66 | 50至80 | 100 | 100至133 | [S1]
| 工作电压（V） | 3.6 | 2.5 | 3.3 | 3.3 |  | 3.3 | [S1]
| 功率消耗（W） | 10（80 MHz） | 6 | 1.2 | 3（80 MHz） | 3.5 | 17.5 | [S1]
| 制程（micrometer） | 0.6 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | [S1]
| 芯片大小（mm²） | 120 | 74 | 50 | 120 | 98 | 197 | [S1]
| 晶体管数 | 280万 | 280万 | 100万 | 160万 | 260万 | 360万 | [S1]
| 缓存大小（KB） | 共用32 | 共用32 | 数据、指令各4 | 数据、指令各8 | 数据、指令各16 | 数据、指令各16 | [S1]
| 总线 | 地址32位，数据64位 | 地址32位，数据64位 | 地址32位，数据64位 | 地址32位，数据32或64位 | 地址32位，数据32或64位 | 地址32位，数据32或64位 | [S1]
| SPECint92 | 85（80 MHz） | 105 | 40 | 75（80 MHz） | 120 | 200（133MHz） | [S1]
| SPECfp92 | 105（80 MHz） | 125 | - | 85（80 MHz） | 105 | 200（133MHz） | [S1]

[S1]

### PowerPC 604e

PowerPC 604e于1996年7月推出，改进了内存子系统与分支预测，而内存总线时钟为66MHz，有510万个晶体管，采用0.35 μm CMOS制造，芯片大小为148平方毫米或96平方毫米，工作时钟为166至233 MHz，在233 MHz时功率消耗为16-18 W。与前代产品相比，性能提高了25%。[S1]

#### PowerPC 604ev "Mach5"

PowerPC 604ev、604r（或称“Mach 5”）于1997年8月推出，是制程改进为0.25 μm CMOS的PowerPC 604e，芯片面积减至47平方毫米，工作时钟提升至250到400 MHz，内存总线速度为100MHz，而功率消耗在250 MHz时则为6 W。虽然苹果公司在1998年转而使用PowerPC 750，但IBM仍在其RS/6000工作站的入门级型号中使用PowerPC 604ev。[S1]

### PowerPC 7xx

第三代的PowerPC微处理器是PowerPC 7xx，由苹果公司称为PowerPC G3，于1997年11月10日推出；G3一词常被使用于苹果电脑的机种，例如PowerBook G3、彩色iMac、iBook和蓝色以及白色的Power Macintosh G3。[S1] PowerPC 7xx系列由于低功耗与小尺寸，是笔记本电脑的理想选择，一直使用到麦金塔转用x86处理器之前，而且也广泛使用于嵌入式设备，如打印机、路由器、存储设备、太空船和游戏机。[S1] 但7xx系列的弱点在于并未支持对称多处理、缺乏单指令流多数据流能力，以及相对较弱的浮点运算功能。摩托罗拉的74xx系列处理器针对这些问题进行设计与改进。[S1]

### PowerPC 7400

PowerPC 7400（代号“Max”）于1999年8月推出，又被称为“G4”，工作时钟为350至500 MHz，有1050万个晶体管，以摩托罗拉的0.20 μm HiPerMOS6制造，芯片尺寸为83 mm²，采用铜制程。[S1] 但摩托罗拉曾向苹果承诺将提供工作时钟500 MHz的芯片，但初期良率过低，使得苹果无法推出宣传的500 MHz之PowerMac G4，在摩托罗拉处理此问题时，苹果只好将PowerMac G4型号的工作时钟从400、450和500 MHz降到350、400和450 MHz。[S1] 该事件导致苹果与摩托罗拉的关系出现裂痕，据报道苹果向IBM寻求帮助，以提高摩托罗拉7400系列的产量。[S1] 后来在2000年2月16日苹果的PowerMac 500 MHz型号上市。[S1]

最后一款使用G4的桌上型麦金塔是Mac Mini；笔记本电脑的iBook G4与PowerBook G4后来都改用英特尔x86处理器。[S1] 但还有其他平台也使用PowerPC G4处理器，例如AmigaOne系列机种和Genesi的Pegasos；而PowerPC G4也常用于嵌入式系统，例如路由器、电信交换机、影像与媒体处理、航空电子设备和军事应用；其AltiVec及对称多处理功能在这些领域可发挥所长。[S1]

### PowerPC 970

PowerPC 970、PowerPC 970FX和PowerPC 970MP是IBM于2002年推出的64位元PowerPC处理器，而苹果公司在采用此系列处理器的麦金塔，称之为PowerPC G5。[S1] 本系列是IBM和苹果以POWER4为基础合作开发的，项目代号为GP-UL或Giga Processor Ultra Light。[S1] 苹果推出PowerMac G5时曾表示这是一项为期五年的合作成果，且有多世代的发展路线图。[S1] 但一年以后苹果不得不收回推出使用3 GHz处理器之PowerMac G5的承诺，IBM也无法将功耗降低到可供笔记本电脑所用的水准，使得苹果的笔记本电脑仍然采用PowerPC G4。[S1] 最终苹果转用x86处理器于麦金塔电脑。[S1] 此外，IBM的JS20/JS21刀锋服务器和一些低端工作站和System p服务器使用了PowerPC 970。[S1] 有些高端嵌入式系统（如Mercury的Momentum XSA-200）也使用了PowerPC 970。[S1] IBM也将PowerPC 970内核授权其他厂商用于自定义使用。[S1]

## 产品应用

较广为人知的产品应用包含：
- 苹果公司：Power Macintosh系列、PowerBook系列（1995年以后的产品，开始使用PowerPC 603系列）、iBook系列、iMac系列（2005年以前的产品）、eMac系列产品。[S1]
- 任天堂：GameCube、Wii和Wii U。[S1]
- 微软：Xbox 360。[S1]
- 索尼：PlayStation 3。[S1]

## 来源

- [S1] PowerPC - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/PowerPC（抓取日期：2026-07-27）
