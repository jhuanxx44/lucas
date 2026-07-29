---
title: RDRAM
type: concept
industry: 半导体
as_of: '2026-07-27'
summary: RDRAM（Direct Rambus DRAM）是Rambus公司设计的同步DRAM，采用双沿传输和RIMM封装，曾在PC、游戏主机和显卡中应用，但因高延迟、高成本和专利授权问题逐渐被DDR
  SDRAM取代。
source_ids:
- S1
---

# RDRAM

## 定义与特点

Direct Rambus DRAM（也称DRDRAM或RDRAM）是Rambus公司设计制造的一种同步DRAM [S1]。其模组封装称为RIMM（Rambus In-line Memory Module）[S1]。RDRAM在时钟信号的上升沿和下降沿均可进行数据传输 [S1]。由于销售需要，命名方式为时钟频率的二倍（避免与DDR内存命名方式重复），例如400MHz规格的Rambus被命名为PC800，提供1600MB/s传输速率 [S1]。相比之下，PC-133 SDRAM工作于133MHz，使用64bit的168针DIMM插座，提供1066MB/s传输速率 [S1]。

## 实际应用

### 个人电脑

1999年发表了第一片支持RDRAM的主板，这些产品与PC800 RDRAM兼容，以400MHz频率工作并具有1600MB/s传输速率，使用184针的RIMM插座 [S1]。如果主板使用双通道架构的内存子系统，则需要将所有内存通道都插上RIMM [S1]。16位元单通道提供1条内存通道，32位元则提供2条 [S1]。因此，在仅支持16位元RIMM的双通道主板上，需要成对安装RIMM；而支持32位元RIMM的双通道主板则可以逐条安装 [S1]。16位元与32位元的RIMM不可混插 [S1]。

模组规格表（从快照中复制关键部分）[S1]：

| 规格命名 | 汇流排宽度 | 通道 | 时脉 | 传输速度 |
| --- | --- | --- | --- | --- |
| PC600 | 16Bit | 单通道 RIMM | 300 MHz | 1200 MB/s | [S1]
| PC700 | 16Bit | 单通道 RIMM | 355 MHz | 1420 MB/s | [S1]
| PC800 | 16Bit | 单通道 RIMM | 400 MHz | 1600 MB/s | [S1]
| PC1066 (RIMM 2100) | 16Bit | 单通道 RIMM | 533 MHz | 2133 MB/s | [S1]
| PC1200 (RIMM 2400) | 16Bit | 单通道 RIMM | 600 MHz | 2400 MB/s | [S1]
| RIMM 3200 | 32Bit | 双通道 RIMM | 400 MHz | 3200 MB/s | [S1]
| RIMM 4200 | 32Bit | 双通道 RIMM | 533 MHz | 4200 MB/s | [S1]
| RIMM 4800 | 32Bit | 双通道 RIMM | 600 MHz | 4800 MB/s | [S1]
| RIMM 6400 | 32Bit | 双通道 RIMM | 800 MHz | 6400 MB/s | [S1]

### 电视游戏主机

Rambus的RDRAM最初在1996年的任天堂电视游戏主机Nintendo 64（N64）上使用 [S1]。N64使用4MB、9位元汇流排、工作于500MHz的RDRAM，达到562.5MB/s的传输速度 [S1]。受惠于RDRAM简单的设计，N64得以确保较大的内存传输速度；而受惠于RDRAM狭窄的汇流排宽度，主板的电路设计师得以使用单纯的设计方式降低成本 [S1]。然而，在随机存取方面延迟较高的缺点为人所诟病 [S1]。N64为RDRAM模组使用了一套被动散热系统 [S1]。

SONY PlayStation 2使用32MB的RDRAM主存储器，具备双通道架构可达到3200MB/s的传输速度 [S1]。

SONY PlayStation 3使用256MB、64bit汇流排、工作于400MHz（有效时脉达到3.2GHz）的XDR DRAM（RDRAM的后继产品），达到204.8Gbit/s（25.6GB/s）的高速资料传输速率，具有8倍于DDR-400 SDRAM的传输速度 [S1]。

### 显示卡

Cirrus Logic公司在Laguna显示芯片家族中的两个产品使用RDRAM，分别是仅有2D的5462和有3D加速的2D芯片5464 [S1]。使用16Bit单通道，提供600MB/s的传输速度 [S1]。该芯片不仅利用RDRAM的高传输速度，更提供了成本方面的优点 [S1]。此芯片在创新科技的Graphics Blaster MA3xx系列等使用 [S1]。

## 性能

与当时其他内存规格相比较，Rambus由于增加了若干等待时间，以及在发热和制造上的复杂，导致成本较高 [S1]。RDRAM也被批评印模尺寸太大，16M需要百分之10-20，64M需要约百分之5的接口，因此需要罚锾 [S1]。

PC800 RDRAM工作在45纳秒的等待时间，与当时的DRAM技术相比较高的等待时间 [S1]。RDRAM的内存芯片比SDRAM芯片发出更大的热量，所以所有的RIMM皆需要散热片 [S1]。RDRAM每片内存芯片皆内建控制器，与北桥芯片上配置单一的内存控制器的SDRAM相比制造上大幅复杂 [S1]。RDRAM由于较高的制造成本和授权费，与PC-133 SDRAM相比价格达到了2-3倍 [S1]。

复数RIMM在同一个内存通道安装的场合，对性能的影响比SDRAM的设计要高，与SDRAM的母模式途经1-2个芯片相比，RDRAM在较远的内存模组上芯片必须要经过近乎与内存控制器物理配置相当的所有内存芯片 [S1]。

最普通的Rambus内存控制器的设计，是将内存模组成对安装做为前提 [S1]。剩下未使用的内存插座必须安装CRIMM [S1]。追加的CRIMM模组并不会增加内存的容量，只是为了不使主板上的信号发生反射而传达的相对于终端抵抗的信号 [S1]。

伴随Intel 840（Pentium III）、Intel 850（Pentium 4）、Intel 860（Pentium 4 Xeon）芯片组的登场，Intel增加了32bit双通道PC800 RDRAM的支持 [S1]。随后，i850E芯片组导入了PC1066 RDRAM，双通道时的合计传输速度扩大到4264MB/s [S1]。

2000年登场的PC-2100 DDR SDRAM工作于133MHz，有效时脉266MHz，使用184针DIMM插座的64bit汇流排提供2100MB/s的性能 [S1]。

2002年，Intel发布了E7205 Granitebay芯片组，导入了双通道DDR内存，同与之竞争的RDRAM相比，可以在更低的等待时间下，提供4200MB/s的合计传输速度 [S1]。

### 基准测试

RDRAM为了达到800MHz的速度，与拥有64bit汇流排的现代SDRAM DIMM不同，内存模组只可以工作在16bit汇流排下 [S1]。然而，Intel 820登场时的RDRAM模组只能工作在较慢的时脉，所有产品都无法工作在800MHz [S1]。

1998年的基准测试中，大部分的应用程式在RDRAM下速度偏低 [S1]。RDRAM使用UMA比SDRAM产品相比仅仅是高速，Intel 820并不是低阶产品，更没有开发使用RDRAM的低阶制品 [S1]。因此，RDRAM对于最终用户来说没有优势 [S1]。

1999年，使用Intel 840、Intel 820、Intel 440BX的基准测试中，由于使用Rambus芯片组而获得性能提高的，除了工作站用途之外，与440BX芯片组和PC-133 SDRAM相比，价钱的大幅提高并不正常 [S1]。

2002年，单通道DDR SDRAM模组和SiS 648组合时，实际的应用程式性能与双通道1066MHz RDRAM和Intel 850E的架构相抗衡 [S1]。此后更有可使用双通道的DDR400 SDRAM模组的芯片组登场 [S1]。

## PC市场上的RDRAM

1996年11月，Rambus与Intel签订了开发与授权协议 [S1]。在与DDR SDRAM比较中认识了RDRAM的优越性后，Intel对于Wintel开发社群发表了自公司微处理器仅会支援Rambus内存接口的声明，Intel获取了Rambus公司以每股10美元100万股股票的购买权 [S1]。

1998年，Intel为了加速Direct RDRAM的导入，计划了对Micron Technology进行5亿美元的资本投资 [S1]。作为额外的投资，还有1999年支付给Samsung的1亿美元等 [S1]。

应对内存过渡时期，Intel在Intel 82x芯片组上使用Memory Transfer Hub（MTH）以支持PC-133 SDRAM DIMM [S1]。2000年，由于MTH在同时交换时，发生了不明原因的停止工作，突发重新启动的电气噪音，Intel召回了搭载MTH的Intel 820主板 [S1]。从此，Intel 820主板没有再搭载过MTH [S1]。

2000年，Intel将零售的Pentium 4 CPU与两支RIMM配套发售，援助RDRAM [S1]。然而，Intel在翌年的2001年起逐渐停止了对Rambus的支持 [S1]。

2003年，Intel发布了Intel 865和Intel 875芯片组，作为取代Intel 850的高端芯片组产品 [S1]。此外，未来的内存发展计划中并未包含Rambus [S1]。

几乎没有DRAM生产厂商取得了RDRAM的生产许可证，而取得了技术许可证的公司就连仅仅生产满足市场需要的RIMM也失败了，在内存价格高涨的2002年RIMM也设定了较SDRAM DIMM高的价格 [S1]。

## 来源

- [S1] RDRAM - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/RDRAM（抓取日期：2026-07-27）
